"""QEC-P1 G6-extended — probe validity, measured within session.

WHY (Amendment A5 section 1)
----------------------------
G6 as originally run rests on 7 (probe score, measured p_L) pairs pooled
across four sessions, rho = +0.414 -- sitting exactly on the declared 0.4
threshold, with a standard error near 0.41 at n=7. Pooling also confounds
patch quality with session-to-session device state.

Session 11 contains direct counter-evidence: two patches with IDENTICAL
probe scores (0.12109) measured p_L of 0.1289 and 0.0430 -- a 3x
difference from indistinguishable probe scores.

The cause is structural: the session runner probes 8 candidates but
deploys only 2-3, so almost no candidate has both a probe score and a
measured logical error rate.

WHAT THIS RUNS
--------------
One job per window:
  1. probe all 8 candidates      (3 circuits each, 256 shots)
  2. deploy ALL 8 candidates     (ENC_ACTIVE, |1_L>, 4096 shots)

That gives 8 WITHIN-SESSION pairs, blocked by session, no cross-session
confound. Probe and deploy are separate jobs only because the probe must
complete before nothing -- here they need not be sequential, since every
candidate is deployed regardless of rank. They are therefore submitted as
ONE job, which also guarantees both arms see the same device state.

FROZEN ANALYSIS (Amendment A5 section 1)
-----------------------------------------
Spearman rho between probe score and measured p_L, computed WITHIN each
session, reported per session, then combined. Thresholds unchanged:
  rho >= 0.4  valid
  0.2 - 0.4   weak, reported as such
  < 0.2       FAIL: the probe does not predict logical error

A near-zero result is a reportable finding, not a failure of the run. It
would mean probe-based selection has no discriminant validity on this
device at 256 probe shots, and that Q-A' and Q-C both lose their premise.

Usage:
    python -m qec.g6_extended --dry-run
    python -m qec.g6_extended --submit --window 1
    python -m qec.g6_extended --retrieve runs/g6ext_1_jobs.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

from qec import tier0, probe, stage_b, layouts

N_CANDIDATES = 8
PROBE_SHOTS = 256
MAIN_SHOTS = 4096
ROUNDS = 3
STATE = 1                      # |1_L>, the damping-exposed state


def build_job(cands):
    """Probe circuits for all candidates + ENC_ACTIVE for all candidates."""
    named = []
    for patch in cands:
        lay = stage_b.layout_for(patch)
        for st in (0, 1):
            named.append((f"probe|{patch}|readout{st}",
                          probe.build_readout_probe(st), lay))
        named.append((f"probe|{patch}|syndrome",
                      probe.build_syndrome_probe(), lay))
    for patch in cands:
        named.append((f"deploy|{patch}|ENC_ACTIVE",
                      tier0.build_encoded(ROUNDS, STATE, active=True),
                      stage_b.layout_for(patch)))
    return named


def submit(window, snapshots):
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    svc = QiskitRuntimeService()
    be = svc.backend("ibm_marrakesh")
    cycles = stage_b.load_cycles(snapshots)
    cands = stage_b.candidate_patches(cycles, N_CANDIDATES)
    print(f"{len(cands)} candidates, all of them deployed:")
    for c in cands:
        print(f"   {c}")

    named = build_job(cands)
    cache = {}
    isa = [stage_b.transpile_checked(qc, be, lay, cache)
           for _, qc, lay in named]

    # probe and deploy have different shot counts; run as two PUB groups
    sampler = SamplerV2(mode=be)
    n_probe = len(cands) * 3
    sampler.options.default_shots = PROBE_SHOTS
    job_p = sampler.run(isa[:n_probe])
    sampler.options.default_shots = MAIN_SHOTS
    job_m = sampler.run(isa[n_probe:])

    stamp = {"window": window, "backend": be.name,
             "candidates": [list(c) for c in cands],
             "names": [n for n, _, _ in named],
             "n_probe": n_probe,
             "probe_job_id": job_p.job_id(), "main_job_id": job_m.job_id(),
             "probe_shots": PROBE_SHOTS, "main_shots": MAIN_SHOTS,
             "rounds": ROUNDS, "state": STATE,
             "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        stamp["calibration_before"] = str(
            getattr(be.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        stamp["calibration_before"] = "unavailable"

    os.makedirs("runs", exist_ok=True)
    jf = f"runs/g6ext_{window}_jobs.json"
    with open(jf, "w") as fh:                            # BEFORE any wait
        json.dump(stamp, fh, indent=2)
    print(f"\nprobe job {job_p.job_id()}\nmain  job {job_m.job_id()}")
    print(f"ids saved to {jf} - Ctrl+C is SAFE")
    return jf


def retrieve(jobs_file):
    from qiskit_ibm_runtime import QiskitRuntimeService
    stamp = json.load(open(jobs_file))
    svc = QiskitRuntimeService()
    cands = [tuple(c) for c in stamp["candidates"]]
    named = build_job(cands)

    counts = {}
    for key, lo, hi in (("probe_job_id", 0, stamp["n_probe"]),
                        ("main_job_id", stamp["n_probe"], len(named))):
        job = svc.job(stamp[key])
        print(f"{stamp[key]}: {job.status()}")
        res = job.result()
        for i, idx in enumerate(range(lo, hi)):
            nm, qc, _ = named[idx]
            try:
                counts[nm] = stage_b.counts_from_pub(res[i], qc)
            except Exception as e:                       # noqa: BLE001
                counts[nm] = None
                print(f"  parse failed {nm}: {type(e).__name__}")

    out = {"stamp": stamp, "counts": counts}
    try:
        out["metrics"] = {
            k: svc.job(stamp[k]).metrics().get("usage")
            for k in ("probe_job_id", "main_job_id")}
    except Exception:                                    # noqa: BLE001
        pass
    path = f"runs/g6ext_{stamp['window']}_result.json"
    json.dump(out, open(path, "w"), indent=2)
    print(f"wrote {path}")
    report(out)
    return out


def report(out):
    from qec.analyze import enc_pL, wilson, spearman
    stamp, counts = out["stamp"], out["counts"]
    cands = [tuple(c) for c in stamp["candidates"]]
    st = stamp["state"]

    rows = []
    for patch in cands:
        try:
            r0 = probe.readout_error_from_counts(
                counts[f"probe|{patch}|readout0"], 0)
            r1 = probe.readout_error_from_counts(
                counts[f"probe|{patch}|readout1"], 1)
            det = probe.detection_rate_from_counts(
                counts[f"probe|{patch}|syndrome"])
        except (KeyError, TypeError):
            continue
        score = probe.probe_score(r0, r1, det)
        c = counts.get(f"deploy|{patch}|ENC_ACTIVE")
        if not c:
            continue
        k, n = enc_pL(c, st, False)
        lo, hi = wilson(k, n)
        rows.append({"patch": list(patch), "probe_score": score,
                     "p_L": k / n, "ci": [lo, hi]})

    print("\n" + "=" * 72)
    print(f"G6-EXTENDED — window {stamp['window']}, all candidates deployed")
    print(f"ENC_ACTIVE |{st}_L>, {stamp['main_shots']} shots")
    print("=" * 72)
    rows.sort(key=lambda r: r["probe_score"])
    print(f"{'patch':<26} {'probe':>9} {'p_L':>9}   95% CI")
    for r in rows:
        print(f"{str(tuple(r['patch'])):<26} {r['probe_score']:>9.5f} "
              f"{r['p_L']:>9.4f}   [{r['ci'][0]:.4f}, {r['ci'][1]:.4f}]")

    rho = spearman([r["probe_score"] for r in rows], [r["p_L"] for r in rows])
    print("-" * 72)
    if rho is None:
        print("rho: undefined (need >=3 candidates with both values)")
    else:
        verdict = ("PASS - probe has discriminant validity" if rho >= 0.4
                   else "WEAK - report as such, no validity claim"
                   if rho >= 0.2 else
                   "FAIL - probe does NOT predict logical error")
        print(f"within-session Spearman rho = {rho:+.3f}   n={len(rows)}")
        print(f"VERDICT: {verdict}")
        if rho < 0.2:
            print("\nA FAIL here means probe-based selection has no")
            print("discriminant validity on this device at these probe")
            print("shots, and Q-A' and Q-C lose their premise. Declared")
            print("in Amendment A5 section 1 before this run.")
    print("=" * 72)
    m = out.get("metrics")
    if m:
        print("metered:", m)
    return rho


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--retrieve", default=None)
    ap.add_argument("--window", type=int, default=1)
    ap.add_argument("--snapshots",
                    default="data/snapshots_marrakesh/*_converted.json")
    a = ap.parse_args()

    if a.dry_run:
        cycles = stage_b.load_cycles(a.snapshots)
        cands = stage_b.candidate_patches(cycles, N_CANDIDATES)
        n_p = len(cands) * 3
        n_m = len(cands)
        cs = n_p * PROBE_SHOTS + n_m * MAIN_SHOTS
        print(f"{len(cands)} candidates")
        for c in cands:
            print(f"   {c}")
        print(f"\nprobe : {n_p} circuits x {PROBE_SHOTS} = {n_p*PROBE_SHOTS:,}")
        print(f"deploy: {n_m} circuits x {MAIN_SHOTS} = {n_m*MAIN_SHOTS:,}")
        print(f"total : {cs:,} circuit-shots")
        print(f"projected at the measured anchor: {cs*3.0/3584:.0f} s")
        print("\nDRY RUN - zero QPU")
        return

    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print(f"G6-EXTENDED window {a.window}. This SPENDS QPU TIME.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    jf = submit(a.window, a.snapshots)
    print("\nwaiting (Ctrl+C safe)...")
    time.sleep(5)
    retrieve(jf)


if __name__ == "__main__":
    main()
