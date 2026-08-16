"""QEC-P1 Q-B supplement — duration-matched BARE baseline.

WHY THIS EXISTS
---------------
Deviation D-B3: sessions 11-14 executed the BARE arm via
tier0.build_bare(state) with delay_dt defaulting to 0. The circuit was
therefore prepare-and-measure (depth 2, zero delay instructions) while
ENC_ACTIVE ran three syndrome-extraction rounds (depth 31 logical, 74
transpiled). The duration matching required by PREREGISTRATION section
3.3 -- added specifically because the council flagged an unmatched bare
baseline as rigging the comparison -- was never applied.

Consequence: every S = p_BARE / p_L value from those sessions compares an
instantaneous measurement against a multi-round encoded circuit. Those
numbers are not the specified break-even comparison and are biased hard
in BARE's favour.

WHAT THIS RUNS
--------------
For each policy patch, on the SAME device:
  1. transpile ENC_ACTIVE onto the patch, schedule it, read its real
     duration in dt from the live target
  2. build BARE with delay_dt set to that duration
  3. execute matched BARE on all three data qubits, both logical states
  4. also re-execute ENC_ACTIVE alongside, so S is computed from arms
     measured in the SAME job rather than across days

Step 4 matters: pairing matched-BARE against the ENC_ACTIVE numbers from
sessions 11-14 would compare arms measured under different device states.
Running both here keeps the comparison within one job.

HONEST STATUS OF THE RESULT
---------------------------
This is a SUPPLEMENTARY measurement, not a repair of the original
sessions. It is a single window, so it carries no cross-session
replication and no paired-by-session structure. Q-B is reported from it
as a single-window estimate with that limitation stated, and the original
unmatched S values are reported as void.

Usage:
    python -m qec.qb_supplement --dry-run
    python -m qec.qb_supplement --submit
    python -m qec.qb_supplement --retrieve runs/qb_supplement_jobs.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

from qec import tier0, stage_b

SHOTS = 4096
ROUNDS = 3
JOBS_FILE = "runs/qb_supplement_jobs.json"
OUT_FILE = "runs/qb_supplement_result.json"

# The three policy patches actually deployed across sessions 11-14.
PATCHES = {
    "P_archive": (1, 2, 3, 4, 5),
    "P_probe_s11": (2, 3, 4, 5, 6),
    "P_probe_s14": (10, 11, 12, 13, 14),
}


def scheduled_duration(backend, layout):
    """Duration in dt of the SYNDROME-EXTRACTION structure (ENC_PASSIVE).

    Qiskit cannot schedule circuits containing control flow:
        TranspilerError: "Some options cannot be used with control flow.
        Got scheduling_method='alap', but the entire scheduling stage is
        not supported."
    ENC_ACTIVE therefore cannot be scheduled directly, and its transpiled
    duration attribute is None.

    We schedule ENC_PASSIVE instead, which carries the identical encoding,
    three rounds of CZ/measure/reset, and final readout -- everything
    except the conditional-branch execution.

    CONSEQUENCE, stated rather than hidden: the matched BARE delay
    UNDER-matches ENC_ACTIVE by the feedforward-branch time, which is
    exactly the quantity that cannot be scheduled. BARE therefore receives
    slightly LESS decoherence exposure than ENC_ACTIVE. That biases
    against the encoded arm, so it makes "encoding helps" harder to claim,
    not easier. For ENC_PASSIVE the match is exact.

    Verified against target instruction durations by hand: cz 17 dt,
    measure 671 dt, reset 680 dt, sx 9 dt give ~5109 dt for the sequence,
    within 3.1% of the scheduler's figure -- so the number is not an
    artifact of the pass.
    """
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    pm = generate_preset_pass_manager(optimization_level=3, backend=backend,
                                      initial_layout=layout,
                                      scheduling_method="alap")
    sched = pm.run(tier0.build_encoded(ROUNDS, 1, active=False))
    dur = getattr(sched, "duration", None)
    if dur is None:
        starts = getattr(sched, "op_start_times", None)
        if starts:
            dur = max(starts)
    return dur, sched


def submit():
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    svc = QiskitRuntimeService()
    be = svc.backend("ibm_marrakesh")

    named, meta = [], []
    for label, patch in PATCHES.items():
        layout = stage_b.layout_for(patch)
        dur, sched = scheduled_duration(be, layout)
        if dur is None:
            raise SystemExit(
                f"{label}: scheduler returned no duration; cannot "
                "duration-match. Do not proceed with an unmatched BARE.")
        dt_s = getattr(be.target, "dt", None)
        us = (dur * dt_s * 1e6) if dt_s else float("nan")
        meta.append({"policy": label, "patch": list(patch),
                     "match_duration_dt": int(dur),
                     "match_duration_us": round(us, 3),
                     "matched_to": "ENC_PASSIVE (control flow unschedulable)",
                     "enc_passive_depth": sched.depth()})
        print(f"{label:<12} {patch}  matched delay = {dur} dt "
              f"({us:.2f} us), from ENC_PASSIVE schedule")

        for st in (0, 1):
            # matched BARE on each of the three data qubits
            for k in range(3):
                qc = tier0.build_bare(st, delay_dt=int(dur))
                if qc.count_ops().get("delay", 0) == 0:
                    raise SystemExit("BARE has no delay; matching failed")
                named.append((f"{label}|BAREMATCH{k}|{st}", qc, [layout[k]]))
            # Both encoded arms in the same job, so S is within-job.
            # ENC_PASSIVE is EXACTLY duration-matched to the BARE delay;
            # ENC_ACTIVE is under-matched by the feedforward-branch time.
            named.append((f"{label}|ENC_PASSIVE|{st}",
                          tier0.build_encoded(ROUNDS, st, active=False), layout))
            named.append((f"{label}|ENC_ACTIVE|{st}",
                          tier0.build_encoded(ROUNDS, st, active=True), layout))

    cache = {}
    isa = [stage_b.transpile_checked(qc, be, lay, cache)
           for _, qc, lay in named]

    sampler = SamplerV2(mode=be)
    sampler.options.default_shots = SHOTS
    job = sampler.run(isa)

    stamp = {"job_id": job.job_id(), "backend": be.name, "shots": SHOTS,
             "rounds": ROUNDS, "names": [n for n, _, _ in named],
             "meta": meta,
             "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        stamp["calibration_before"] = str(
            getattr(be.properties(), "last_update_date", "n/a"))
    except Exception:                                     # noqa: BLE001
        stamp["calibration_before"] = "unavailable"

    os.makedirs("runs", exist_ok=True)
    with open(JOBS_FILE, "w") as fh:                      # BEFORE any wait
        json.dump(stamp, fh, indent=2)
    print(f"\nSUBMITTED {job.job_id()} -> {JOBS_FILE}")
    print("Ctrl+C is SAFE; recover with --retrieve " + JOBS_FILE)
    return job, stamp


def retrieve(jobs_file):
    from qiskit_ibm_runtime import QiskitRuntimeService
    stamp = json.load(open(jobs_file))
    svc = QiskitRuntimeService()
    job = svc.job(stamp["job_id"])
    print(f"{stamp['job_id']}: {job.status()}")
    res = job.result()

    # rebuild circuits in the same order so registers parse correctly
    circs = []
    for label, patch in PATCHES.items():
        for st in (0, 1):
            for _ in range(3):
                circs.append(tier0.build_bare(st, delay_dt=1))
            circs.append(tier0.build_encoded(ROUNDS, st, active=False))
            circs.append(tier0.build_encoded(ROUNDS, st, active=True))

    counts = {}
    for i, nm in enumerate(stamp["names"]):
        try:
            counts[nm] = stage_b.counts_from_pub(res[i], circs[i])
        except Exception as e:                            # noqa: BLE001
            counts[nm] = None
            print(f"  parse failed {nm}: {type(e).__name__}")

    out = {"stamp": stamp, "counts": counts}
    try:
        m = svc.job(stamp["job_id"]).metrics()
        out["metrics"] = {"bss": m.get("bss"), "usage": m.get("usage")}
    except Exception:                                     # noqa: BLE001
        pass
    json.dump(out, open(OUT_FILE, "w"), indent=2)
    print(f"wrote {OUT_FILE}")
    report(out)
    return out


def report(out):
    from qec.analyze import bare_pL, enc_pL, wilson
    counts = out["counts"]
    print("\n" + "=" * 70)
    print("Q-B SUPPLEMENT — DURATION-MATCHED BARE (single window)")
    print("=" * 70)
    for m in out["stamp"]["meta"]:
        print(f"\n{m['policy']} {m['patch']}  matched delay = "
              f"{m['enc_duration_dt']} dt")
        for st in (0, 1):
            bares = []
            for k in range(3):
                c = counts.get(f"{m['policy']}|BAREMATCH{k}|{st}")
                if c:
                    kk, nn = bare_pL(c, st)
                    bares.append(kk / nn)
            if not bares:
                continue
            mean_bare = sum(bares) / len(bares)
            print(f"  |{st}_L>  BARE(matched) each={[round(x,4) for x in bares]} "
                  f"mean={mean_bare:.4f}")
            for klass, corr, note in (
                    ("ENC_PASSIVE", True, "exactly matched"),
                    ("ENC_ACTIVE", False, "under-matched by branch time")):
                c = counts.get(f"{m['policy']}|{klass}|{st}")
                if not c:
                    continue
                kk, nn = enc_pL(c, st, corr)
                p_enc = kk / nn
                lo, hi = wilson(kk, nn)
                S = mean_bare / p_enc if p_enc > 0 else None
                print(f"         {klass:<12} p_L={p_enc:.4f} "
                      f"[{lo:.4f}, {hi:.4f}]  ({note})")
                if S:
                    verdict = "encoding HELPS" if S > 1 else "overhead dominates"
                    print(f"                      S = {S:.3f}   {verdict}")
    print("\n" + "=" * 70)
    print("LIMITATION: single window, no cross-session replication, not")
    print("paired by session. The unmatched S values from sessions 11-14")
    print("are VOID and are not reported as break-even estimates.")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--retrieve", default=None)
    a = ap.parse_args()

    if a.dry_run:
        n = len(PATCHES) * 2 * 5
        print(f"{len(PATCHES)} patches x 2 states x 5 circuits = {n} circuits")
        print(f"{n} x {SHOTS} shots = {n*SHOTS:,} circuit-shots")
        print(f"projected cost at the measured anchor: "
              f"{n*SHOTS*3.0/3584:.0f} s")
        print("\npatches:")
        for label, patch in PATCHES.items():
            print(f"  {label:<12} {patch}")
        print("\nDRY RUN — zero QPU. The scheduled duration is read from the")
        print("live target at submit time; it cannot be computed offline.")
        return

    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print("Q-B SUPPLEMENT — duration-matched BARE")
    print("This SPENDS QPU TIME.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    job, stamp = submit()
    print("\nwaiting (Ctrl+C safe)...")
    job.result()
    retrieve(JOBS_FILE)


if __name__ == "__main__":
    main()
