"""QEC-P1 — powered E4 re-test (Amendment A8).

WHY
---
E4 was 12/12 negative in sessions 11-14 (mean ~ -0.024). The DUMMY_FF run
at 4096 shots/arm gave -0.0042, +0.0017, -0.0139: two of three favouring
ACTIVE, one reversing, and every interval overlapping. Resolving a 0.005
difference at p ~ 0.07 needs ~20,000 shots per arm; 4096 was ~5x short.

WHAT THIS DOES
--------------
Same three arms, same three patches, |1_L>, but 5 repeats x 4096 = 20,480
shots per arm, interleaved repeat-major so every arm spans the job.
Repeats also let the Q-E chi-square check within-job homogeneity BEFORE
pooling, rather than assuming it.

WHAT IT CANNOT DO
-----------------
Explain why sessions 11-14 showed four times the magnitude. Q-E measured
25-31% drift between windows, so that discrepancy is consistent with the
device having moved. Settling it needs this protocol in several windows;
this is window 1.

Usage:
    python -m qec.e4_powered --dry-run
    python -m qec.e4_powered --submit --window 1
    python -m qec.e4_powered --retrieve runs/e4pow_1_jobs.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time

from qec import tier0, stage_b

PATCHES = [(1, 2, 3, 4, 5), (2, 3, 4, 5, 6), (10, 11, 12, 13, 14)]
ARMS = ["ENC_PASSIVE", "DUMMY_FF", "ENC_ACTIVE"]
REPEATS = 5
SHOTS = 4096                    # x REPEATS = 20,480 per arm
ROUNDS = 3
STATE = 1


def make_circuit(arm):
    if arm == "ENC_PASSIVE":
        return tier0.build_encoded(ROUNDS, STATE, active=False)
    if arm == "DUMMY_FF":
        return tier0.build_encoded(ROUNDS, STATE, active=True, dummy_ff=True)
    return tier0.build_encoded(ROUNDS, STATE, active=True)


def build_named():
    """Repeat-major so each arm spans the whole job, not a block."""
    named = []
    for r in range(REPEATS):
        for patch in PATCHES:
            lay = stage_b.layout_for(patch)
            for arm in ARMS:
                named.append((f"{patch}|{arm}|r{r}", make_circuit(arm), lay))
    return named


def diff_ci(k1, n1, k2, n2, z=1.96):
    """Normal-approximation interval on a difference of proportions.

    Adequate at n ~ 20k; the counts are far from 0 and 1.
    """
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return d, (d - z * se, d + z * se), se


def submit(window):
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    svc = QiskitRuntimeService()
    be = svc.backend("ibm_marrakesh")
    named = build_named()

    cache = {}
    isa = []
    for nm, qc, lay in named:
        t = stage_b.transpile_checked(qc, be, lay, cache)
        n_src = qc.count_ops().get("if_else", 0)
        if n_src and t.count_ops().get("if_else", 0) != n_src:
            raise SystemExit(f"{nm}: conditionals not preserved; stop.")
        isa.append(t)

    sampler = SamplerV2(mode=be)
    sampler.options.default_shots = SHOTS
    job = sampler.run(isa)

    stamp = {"window": window, "patches": [list(p) for p in PATCHES],
             "arms": ARMS, "repeats": REPEATS, "shots": SHOTS,
             "shots_per_arm": REPEATS * SHOTS,
             "rounds": ROUNDS, "state": STATE,
             "names": [n for n, _, _ in named], "job_id": job.job_id(),
             "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        stamp["calibration"] = str(
            getattr(be.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        pass
    os.makedirs("runs", exist_ok=True)
    jf = f"runs/e4pow_{window}_jobs.json"
    json.dump(stamp, open(jf, "w"), indent=2)
    print(f"SUBMITTED {job.job_id()} -> {jf}")
    print(f"{len(named)} circuits, {stamp['shots_per_arm']:,} shots per arm")
    return jf


def retrieve(jobs_file):
    from qiskit_ibm_runtime import QiskitRuntimeService
    from qec.analyze import enc_pL
    stamp = json.load(open(jobs_file))
    svc = QiskitRuntimeService()
    job = svc.job(stamp["job_id"])
    print(f"{stamp['job_id']}: {job.status()}")
    res = job.result()
    named = build_named()

    cells = {}
    for i, (nm, qc, _) in enumerate(named):
        try:
            c = stage_b.counts_from_pub(res[i], qc)
            corr = "|ENC_PASSIVE|" in nm          # offline-decode passive only
            k, n = enc_pL(c, stamp["state"], corr)
            cells[nm] = {"k": k, "n": n}
        except Exception as e:                           # noqa: BLE001
            print(f"  parse failed {nm}: {type(e).__name__}")

    out = {"stamp": stamp, "cells": cells}
    try:
        out["metrics"] = job.metrics().get("usage")
    except Exception:                                    # noqa: BLE001
        pass
    path = f"runs/e4pow_{stamp['window']}_result.json"
    json.dump(out, open(path, "w"), indent=2)
    print(f"wrote {path}")
    report(out)
    return out


def report(out):
    from qec.analyze import wilson
    from qec.stability import chi2_homogeneity
    stamp, cells = out["stamp"], out["cells"]
    print("\n" + "=" * 76)
    print(f"POWERED E4 RE-TEST — window {stamp['window']}, "
          f"{stamp['shots_per_arm']:,} shots per arm")
    print("=" * 76)

    for p in stamp["patches"]:
        patch = tuple(p)
        print(f"\n{patch}")
        pooled = {}
        for arm in stamp["arms"]:
            reps = [cells.get(f"{patch}|{arm}|r{r}")
                    for r in range(stamp["repeats"])]
            reps = [x for x in reps if x]
            if not reps:
                continue
            ks = [x["k"] for x in reps]
            ns = [x["n"] for x in reps]
            K, N = sum(ks), sum(ns)
            chi2, df, pv = chi2_homogeneity(ks, ns)
            lo, hi = wilson(K, N)
            pooled[arm] = (K, N)
            flag = "" if pv > 0.05 else "  <- heterogeneous, caveat attached"
            print(f"  {arm:<14} p_L={K/N:.4f} [{lo:.4f}, {hi:.4f}]  "
                  f"n={N:,}  chi2 p={pv:.3f}{flag}")

        if len(pooled) < 3:
            continue
        kp, np_ = pooled["ENC_PASSIVE"]
        kd, nd = pooled["DUMMY_FF"]
        ka, na = pooled["ENC_ACTIVE"]
        for label, (k1, n1), (k2, n2) in (
                ("net E4 (ACTIVE-PASSIVE)", (ka, na), (kp, np_)),
                ("control-path cost      ", (kd, nd), (kp, np_)),
                ("correction benefit     ", (ka, na), (kd, nd))):
            d, (lo, hi), se = diff_ci(k1, n1, k2, n2)
            excl = "excludes 0" if (lo > 0 or hi < 0) else "INCLUDES 0"
            print(f"  {label} {d:+.4f}  [{lo:+.4f}, {hi:+.4f}]  {excl}")

    print("\n" + "=" * 76)
    print("READING THIS (A8 section 5, declared before the run)")
    print("=" * 76)
    print("net E4 excludes 0 and negative in all three -> effect exists at")
    print("   this device state, at the magnitude reported here.")
    print("net E4 includes 0 -> no detectable effect at ~20k shots; any")
    print("   true effect is below ~0.005 and sessions 11-14 stands")
    print("   unreplicated at its magnitude.")
    print("signs disagree with intervals excluding 0 -> patch-dependent;")
    print("   E4 cannot be stated as one number.")
    print("\nNo outcome restores E4 to a clean positive. Reported with both")
    print("the original and this re-test in view. Window 1 of a series;")
    print("cross-window variation is a separate question (Q-E: 25-31%).")
    print("=" * 76)
    m = out.get("metrics")
    if m:
        print("metered:", m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--retrieve", default=None)
    ap.add_argument("--window", type=int, default=1)
    a = ap.parse_args()

    if a.dry_run:
        named = build_named()
        cs = len(named) * SHOTS
        print(f"{len(PATCHES)} patches x {len(ARMS)} arms x {REPEATS} repeats "
              f"= {len(named)} circuits")
        print(f"{cs:,} circuit-shots, {REPEATS*SHOTS:,} per arm")
        print(f"projected: {cs*3.0/3584:.0f} s")
        print(f"\nfirst 6 (repeat-major, arms interleaved):")
        for nm, _, _ in named[:6]:
            print("  ", nm)
        p = 0.07
        se = math.sqrt(2*p*(1-p)/(REPEATS*SHOTS))
        print(f"\nat p~{p}, SE on a difference = {se:.5f}")
        print(f"  -> resolvable difference (1.96 SE) = {1.96*se:.5f}")
        print(f"  previous run at {SHOTS} shots resolved only "
              f"{1.96*math.sqrt(2*p*(1-p)/SHOTS):.5f}")
        print("\nDRY RUN - zero QPU")
        return
    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print(f"POWERED E4 RE-TEST window {a.window}. This SPENDS QPU TIME.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    jf = submit(a.window)
    print("waiting (Ctrl+C safe)...")
    time.sleep(5)
    retrieve(jf)


if __name__ == "__main__":
    main()
