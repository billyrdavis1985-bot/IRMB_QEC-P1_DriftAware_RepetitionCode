"""QEC-P1 probe v2 — precision and aggregation test (Amendment A6).

WHAT CHANGED FROM THE DEPLOYED PROBE, AND ONLY THIS
----------------------------------------------------
  1. readout probe shots  256 -> 4096  (stderr on a p=0.01 measurement
     falls from ~62% of the value to ~16%)
  2. score aggregation    all 5 qubits -> the 3 DATA qubits only

The syndrome false-detection probe still runs and is recorded, but is
EXCLUDED from the v2 score so this test isolates the two changes above.

WHY
---
G6-extended found rho = -0.072 between the deployed probe score and
measured p_L across 8 candidates. Probe precision is under-resolved by
arithmetic, independent of any correlation: at 256 shots the composite
carries ~20% error on a sum near 0.10, comparable to the between-patch
spread it must resolve.

DECISION RULE, FROZEN IN A6 SECTION 4
--------------------------------------
  rho >= 0.4   probe v2 has discriminant validity; the G6 failure is
               attributable to precision/aggregation
  0.2 - 0.4    weak; reported as weak; no validity claim
  rho < 0.2    measurement-based selection does not predict logical error
               here even with a well-resolved, correctly-aggregated probe.
               The G6 negative is structural, not a design artifact.

Neither outcome is preferred. The third is the stronger claim.

A pass does NOT reinstate Q-A' or Q-C: those were run with the v1 probe.

Usage:
    python -m qec.probe_v2 --dry-run
    python -m qec.probe_v2 --submit --window 1
    python -m qec.probe_v2 --retrieve runs/probev2_1_jobs.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

from qec import tier0, probe, stage_b

N_CANDIDATES = 8
PROBE_SHOTS = 4096          # was 256
MAIN_SHOTS = 4096
ROUNDS = 3
STATE = 1


def score_v2(readout_errs_0, readout_errs_1) -> float:
    """DATA qubits only, both prepared states. Lower is better.

    Simulator/register order in tier0 is d0,d1,d2 then a0,a1, so indices
    0,1,2 are the data qubits and 3,4 are the ancillas. The v1 score
    summed all five; ancilla readout showed no relation to logical error
    in the exploratory diagnosis, and including it dilutes the data term.
    """
    return sum(readout_errs_0[:3]) + sum(readout_errs_1[:3])


def score_v1(readout_errs_0, readout_errs_1, det) -> float:
    """The deployed score, recomputed here for the secondary comparison."""
    return probe.probe_score(readout_errs_0, readout_errs_1, det)


def build_job(cands):
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
    print(f"{len(cands)} candidates, all probed at {PROBE_SHOTS} shots "
          f"and all deployed:")
    for c in cands:
        print(f"   {c}")

    named = build_job(cands)
    cache = {}
    isa = [stage_b.transpile_checked(qc, be, lay, cache)
           for _, qc, lay in named]

    sampler = SamplerV2(mode=be)
    sampler.options.default_shots = PROBE_SHOTS
    n_probe = len(cands) * 3
    job_p = sampler.run(isa[:n_probe])
    sampler.options.default_shots = MAIN_SHOTS
    job_m = sampler.run(isa[n_probe:])

    stamp = {"window": window, "backend": be.name, "version": "v2",
             "candidates": [list(c) for c in cands],
             "names": [n for n, _, _ in named], "n_probe": n_probe,
             "probe_shots": PROBE_SHOTS, "main_shots": MAIN_SHOTS,
             "rounds": ROUNDS, "state": STATE,
             "probe_job_id": job_p.job_id(), "main_job_id": job_m.job_id(),
             "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        stamp["calibration_before"] = str(
            getattr(be.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        stamp["calibration_before"] = "unavailable"

    os.makedirs("runs", exist_ok=True)
    jf = f"runs/probev2_{window}_jobs.json"
    with open(jf, "w") as fh:
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
        out["metrics"] = {k: svc.job(stamp[k]).metrics().get("usage")
                          for k in ("probe_job_id", "main_job_id")}
    except Exception:                                    # noqa: BLE001
        pass
    path = f"runs/probev2_{stamp['window']}_result.json"
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
        c = counts.get(f"deploy|{patch}|ENC_ACTIVE")
        if not c:
            continue
        k, n = enc_pL(c, st, False)
        lo, hi = wilson(k, n)
        rows.append({"patch": list(patch),
                     "v2": score_v2(r0, r1),
                     "v1": score_v1(r0, r1, det),
                     "det": det,
                     "readout_data": sum(r0[:3]) + sum(r1[:3]),
                     "readout_anc": sum(r0[3:]) + sum(r1[3:]),
                     "p_L": k / n, "ci": [lo, hi]})

    print("\n" + "=" * 76)
    print(f"PROBE v2 — window {stamp['window']}, {stamp['probe_shots']} probe shots")
    print(f"score = readout error, DATA qubits only, both states")
    print("=" * 76)
    rows.sort(key=lambda r: r["v2"])
    print(f"{'patch':<26} {'v2':>8} {'v1':>8} {'det':>7} {'p_L':>8}   95% CI")
    for r in rows:
        print(f"{str(tuple(r['patch'])):<26} {r['v2']:>8.5f} {r['v1']:>8.5f} "
              f"{r['det']:>7.4f} {r['p_L']:>8.4f}   "
              f"[{r['ci'][0]:.4f}, {r['ci'][1]:.4f}]")

    pl = [r["p_L"] for r in rows]
    rho2 = spearman([r["v2"] for r in rows], pl)
    rho1 = spearman([r["v1"] for r in rows], pl)
    rho_det = spearman([r["det"] for r in rows], pl)
    rho_anc = spearman([r["readout_anc"] for r in rows], pl)

    print("-" * 76)
    print(f"PRIMARY   probe v2 (data-qubit readout)  rho = {fmt(rho2)}  n={len(rows)}")
    print(f"secondary probe v1 recomputed here       rho = {fmt(rho1)}")
    print(f"secondary syndrome detection alone       rho = {fmt(rho_det)}")
    print(f"secondary ancilla readout alone          rho = {fmt(rho_anc)}")

    print("\nDECISION (A6 section 4):")
    if rho2 is None:
        print("  undefined — insufficient or constant data")
    elif rho2 >= 0.4:
        print("  PASS — probe v2 has discriminant validity.")
        print("  The G6 failure is attributable to precision/aggregation.")
        print("  This does NOT reinstate Q-A' or Q-C (run with v1).")
    elif rho2 >= 0.2:
        print("  WEAK — reported as weak, no validity claim.")
    else:
        print("  FAIL — measurement-based selection does not predict")
        print("  logical error on this device even with a 16x better")
        print("  resolved, correctly aggregated probe. The G6 negative")
        print("  is STRUCTURAL, not a probe-design artifact.")
    print("\n  n=8, one window. SE on Spearman rho at n=8 is roughly 0.38.")
    print("  A pass is suggestive, not established; a second window")
    print("  follows and is reported separately, not pooled.")
    print("=" * 76)
    m = out.get("metrics")
    if m:
        print("metered:", m)
    return rho2


def fmt(r):
    return "  n/a " if r is None else f"{r:+.3f}"


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
        n_p, n_m = len(cands) * 3, len(cands)
        cs = n_p * PROBE_SHOTS + n_m * MAIN_SHOTS
        print(f"{len(cands)} candidates")
        print(f"probe : {n_p} x {PROBE_SHOTS} = {n_p*PROBE_SHOTS:,}")
        print(f"deploy: {n_m} x {MAIN_SHOTS} = {n_m*MAIN_SHOTS:,}")
        print(f"total : {cs:,} circuit-shots")
        print(f"projected at the measured anchor: {cs*3.0/3584:.0f} s")
        import math
        for p in (0.01,):
            se_old = math.sqrt(p*(1-p)/256)
            se_new = math.sqrt(p*(1-p)/PROBE_SHOTS)
            print(f"\nprecision on a p={p} readout measurement:")
            print(f"  256 shots  -> stderr {se_old:.4f} ({se_old/p*100:.0f}% of value)")
            print(f"  {PROBE_SHOTS} shots -> stderr {se_new:.4f} "
                  f"({se_new/p*100:.0f}% of value)")
        print("\nDRY RUN - zero QPU")
        return

    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print(f"PROBE v2 window {a.window}. This SPENDS QPU TIME.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    jf = submit(a.window, a.snapshots)
    print("\nwaiting (Ctrl+C safe)...")
    time.sleep(5)
    retrieve(jf)


if __name__ == "__main__":
    main()
