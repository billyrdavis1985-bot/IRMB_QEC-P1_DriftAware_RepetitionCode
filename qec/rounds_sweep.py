"""QEC-P1 Q-D — break-even versus syndrome-round count (Amendment A5 section 4).

THE QUESTION
------------
Q-B found, replicated across two windows, that the d=3 bit-flip code
beats a duration-matched physical qubit for |1_L> (S ~ 1.5-2.4) and loses
badly for |0_L> (S ~ 0.08-0.48).

The proposed mechanism: over ~21 us of matched idle a bare |1> relaxes
toward |0>, and those relaxation events are exactly the X-channel bit
flips this code corrects. A bare |0> sits in the ground state and barely
decays, so there is nothing to protect and only overhead to pay.

If that is right, the effect should be DOSE-DEPENDENT IN EXPOSURE TIME.

PRE-DECLARED EXPECTATION (A5 section 4, before any data)
---------------------------------------------------------
The STATE ASYMMETRY, S(|1_L>) - S(|0_L>), should INCREASE with round
count: longer exposure produces more relaxation for the code to correct,
while |0_L> gains nothing from it.

**No directional prediction is made for S alone in either state.**
Correction opportunities and accumulated measurement/reset overhead both
grow with rounds, and their balance is not predictable in advance from
what is known here.

WHAT WOULD COUNT AGAINST THE MECHANISM
---------------------------------------
If the state asymmetry is flat or shrinks with round count, the
relaxation explanation for Q-B is not supported and the |1_L> advantage
needs a different account.

DESIGN
------
One patch, three round counts (1, 3, 5), both logical states, three arms.
The BARE delay is RE-DERIVED per round count from the ENC_PASSIVE
schedule at that count -- a 1-round circuit is much shorter than a
5-round one, so a single fixed delay would break the matching that D-B3
was written to fix.

Decoder verified total and correct at 1, 3 and 5 rounds (4, 64 and 1024
syndrome histories respectively) before submission.

Usage:
    python -m qec.rounds_sweep --dry-run
    python -m qec.rounds_sweep --submit
    python -m qec.rounds_sweep --retrieve runs/qd_jobs.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

from qec import tier0, stage_b

PATCH = (1, 2, 3, 4, 5)         # the constant reference patch throughout
ROUND_COUNTS = [1, 3, 5]
SHOTS = 4096
JOBS_FILE = "runs/qd_jobs.json"


def matched_delay(backend, layout, rounds):
    """Schedule ENC_PASSIVE at THIS round count and read its duration.

    Control flow cannot be scheduled (see D-B3), so ENC_PASSIVE stands in
    for ENC_ACTIVE. It carries the identical encoding, syndrome rounds and
    final readout; only the conditional branches are absent. ENC_ACTIVE is
    therefore under-matched by the branch time, which biases against the
    encoded arm.
    """
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    pm = generate_preset_pass_manager(optimization_level=3, backend=backend,
                                      initial_layout=layout,
                                      scheduling_method="alap")
    sched = pm.run(tier0.build_encoded(rounds, 1, active=False))
    dur = getattr(sched, "duration", None)
    if dur is None:
        starts = getattr(sched, "op_start_times", None)
        if starts:
            dur = max(starts)
    return dur


def build_named(delays):
    named = []
    lay = stage_b.layout_for(PATCH)
    for rounds in ROUND_COUNTS:
        d = delays[rounds]
        for st in (0, 1):
            for k in range(3):
                qc = tier0.build_bare(st, delay_dt=int(d))
                if qc.count_ops().get("delay", 0) == 0:
                    raise SystemExit("BARE delay failed to land; stop.")
                named.append((f"r{rounds}|BARE{k}|{st}", qc, [lay[k]]))
            named.append((f"r{rounds}|ENC_PASSIVE|{st}",
                          tier0.build_encoded(rounds, st, active=False), lay))
            named.append((f"r{rounds}|ENC_ACTIVE|{st}",
                          tier0.build_encoded(rounds, st, active=True), lay))
    return named


def submit():
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    svc = QiskitRuntimeService()
    be = svc.backend("ibm_marrakesh")
    lay = stage_b.layout_for(PATCH)

    delays = {}
    dt_s = getattr(be.target, "dt", None)
    for rounds in ROUND_COUNTS:
        d = matched_delay(be, lay, rounds)
        if d is None:
            raise SystemExit(f"rounds={rounds}: no schedulable duration; stop.")
        delays[rounds] = d
        us = d * dt_s * 1e6 if dt_s else float("nan")
        print(f"  rounds={rounds}: matched delay {d} dt ({us:.2f} us)")

    named = build_named(delays)
    cache = {}
    isa = []
    for nm, qc, l in named:
        t = stage_b.transpile_checked(qc, be, l, cache)
        n_src = qc.count_ops().get("if_else", 0)
        if n_src and t.count_ops().get("if_else", 0) != n_src:
            raise SystemExit(f"{nm}: conditionals not preserved; stop.")
        isa.append(t)

    sampler = SamplerV2(mode=be)
    sampler.options.default_shots = SHOTS
    job = sampler.run(isa)

    stamp = {"patch": list(PATCH), "round_counts": ROUND_COUNTS,
             "delays_dt": {str(k): int(v) for k, v in delays.items()},
             "dt_seconds": dt_s, "shots": SHOTS,
             "names": [n for n, _, _ in named], "job_id": job.job_id(),
             "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        stamp["calibration"] = str(
            getattr(be.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        pass
    os.makedirs("runs", exist_ok=True)
    json.dump(stamp, open(JOBS_FILE, "w"), indent=2)
    print(f"\nSUBMITTED {job.job_id()} -> {JOBS_FILE}")
    return JOBS_FILE


def retrieve(jobs_file):
    from qiskit_ibm_runtime import QiskitRuntimeService
    from qec.analyze import enc_pL, bare_pL
    stamp = json.load(open(jobs_file))
    svc = QiskitRuntimeService()
    job = svc.job(stamp["job_id"])
    print(f"{stamp['job_id']}: {job.status()}")
    res = job.result()
    delays = {int(k): v for k, v in stamp["delays_dt"].items()}
    named = build_named(delays)

    cells = {}
    for i, (nm, qc, _) in enumerate(named):
        try:
            c = stage_b.counts_from_pub(res[i], qc)
            st = int(nm.split("|")[-1])
            if "BARE" in nm:
                k, n = bare_pL(c, st)
            else:
                k, n = enc_pL(c, st, "ENC_PASSIVE" in nm)
            cells[nm] = {"k": k, "n": n, "p_L": k / n}
        except Exception as e:                           # noqa: BLE001
            print(f"  parse failed {nm}: {type(e).__name__}")

    out = {"stamp": stamp, "cells": cells}
    try:
        out["metrics"] = job.metrics().get("usage")
    except Exception:                                    # noqa: BLE001
        pass
    json.dump(out, open("runs/qd_result.json", "w"), indent=2)
    print("wrote runs/qd_result.json")
    report(out)
    return out


def report(out):
    from qec.analyze import wilson, spearman
    import statistics
    stamp, cells = out["stamp"], out["cells"]
    dt_s = stamp.get("dt_seconds") or 4e-9
    print("\n" + "=" * 78)
    print(f"Q-D — BREAK-EVEN vs SYNDROME ROUNDS   patch {tuple(stamp['patch'])}")
    print("=" * 78)

    asym = {}
    for rounds in stamp["round_counts"]:
        d = int(stamp["delays_dt"][str(rounds)])
        print(f"\nrounds = {rounds}   exposure {d} dt = {d*dt_s*1e6:.2f} us")
        S_by_state = {}
        for st in (0, 1):
            bares = []
            for k in range(3):
                c = cells.get(f"r{rounds}|BARE{k}|{st}")
                if c:
                    bares.append(c["p_L"])
            if not bares:
                continue
            mb = statistics.fmean(bares)
            print(f"  |{st}_L>  BARE(matched) mean={mb:.4f} "
                  f"each={[round(x,4) for x in bares]}")
            for arm in ("ENC_PASSIVE", "ENC_ACTIVE"):
                c = cells.get(f"r{rounds}|{arm}|{st}")
                if not c:
                    continue
                lo, hi = wilson(c["k"], c["n"])
                S = mb / c["p_L"] if c["p_L"] > 0 else None
                tag = ("encoding HELPS" if S and S > 1 else "overhead dominates")
                print(f"         {arm:<12} p_L={c['p_L']:.4f} "
                      f"[{lo:.4f}, {hi:.4f}]  S={S:.3f}  {tag}")
                S_by_state.setdefault(arm, {})[st] = S
        for arm, d2 in S_by_state.items():
            if 0 in d2 and 1 in d2:
                asym.setdefault(arm, {})[rounds] = d2[1] - d2[0]

    print("\n" + "-" * 78)
    print("STATE ASYMMETRY  S(|1_L>) - S(|0_L>)   — the pre-declared quantity")
    print("-" * 78)
    for arm, per in asym.items():
        rs = sorted(per)
        vals = [per[r] for r in rs]
        print(f"  {arm:<14} " + "  ".join(
            f"r{r}={v:+.3f}" for r, v in zip(rs, vals)))
        if len(rs) >= 3:
            rho = spearman(rs, vals)
            print(f"  {'':<14} monotone with rounds: rho={rho:+.2f} "
                  f"(n={len(rs)})")

    print("\n" + "=" * 78)
    print("READING THIS (A5 section 4, declared before the run)")
    print("=" * 78)
    print("asymmetry INCREASES with rounds -> consistent with the")
    print("   relaxation mechanism proposed for the Q-B result.")
    print("asymmetry FLAT or SHRINKING -> the relaxation explanation is")
    print("   NOT supported and the |1_L> advantage needs another account.")
    print("\nn=3 round counts, one patch, one window. This tests a")
    print("direction, not a functional form. S alone had no predicted")
    print("direction and is reported without one.")
    print("=" * 78)
    m = out.get("metrics")
    if m:
        print("metered:", m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--retrieve", default=None)
    a = ap.parse_args()

    if a.dry_run:
        n = len(ROUND_COUNTS) * 2 * 5
        print(f"patch {PATCH}, rounds {ROUND_COUNTS}, both states")
        print(f"{len(ROUND_COUNTS)} x 2 states x 5 circuits = {n} circuits")
        print(f"{n} x {SHOTS} = {n*SHOTS:,} circuit-shots")
        print(f"projected: {n*SHOTS*3.0/3584:.0f} s")
        for r in ROUND_COUNTS:
            qc = tier0.build_encoded(r, 1, active=True)
            print(f"  rounds={r}: depth={qc.depth()} cregs={len(qc.cregs)}")
        print("\ndelays are derived from the live schedule at submit time,")
        print("one per round count -- a fixed delay would break matching")
        print("\nDRY RUN - zero QPU")
        return
    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print("Q-D ROUNDS SWEEP. This SPENDS QPU TIME.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    jf = submit()
    print("waiting (Ctrl+C safe)...")
    time.sleep(5)
    retrieve(jf)


if __name__ == "__main__":
    main()
