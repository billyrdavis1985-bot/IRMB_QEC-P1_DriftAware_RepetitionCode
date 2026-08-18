"""QEC-P1 — DUMMY_FF attribution for E4 (Amendment A5 section 3).

THE GAP THIS CLOSES
-------------------
E4 found p_L(ENC_ACTIVE) below p_L(ENC_PASSIVE offline-decoded) in 12 of
12 cells. The design attributes that to in-circuit correction preventing
error accumulation across rounds. But DUMMY_FF -- the diagnostic that
isolates the cost of traversing the conditional-control path without
applying any correction -- ran only in Stage A, never alongside the E4
comparison. E4 therefore describes an effect it cannot attribute.

THE THREE ARMS, all in ONE job so they share a device state
-----------------------------------------------------------
  ENC_PASSIVE   syndromes recorded, no in-circuit action.
                Decoded offline with the same frozen table.
  DUMMY_FF      identical measure-and-conditional structure, but the
                conditional applies X to an ancilla already measured and
                reset this round -- a real gate on a real qubit, so the
                control path and its timing survive transpilation, while
                the data qubits are untouched.
  ENC_ACTIVE    the conditional applies the correction to the data.

FROZEN INTERPRETATION (A5 section 3)
------------------------------------
  control-path cost  = p_L(DUMMY_FF)   - p_L(ENC_PASSIVE offline)
  correction benefit = p_L(ENC_ACTIVE) - p_L(DUMMY_FF)

If the control-path cost is small while ENC_ACTIVE still beats
ENC_PASSIVE substantially, the E4 benefit is attributable to correction
rather than to an artifact of the dynamic-circuit path.

If DUMMY_FF is itself much better than ENC_PASSIVE, then merely running
the conditional structure changes the outcome, and the E4 benefit cannot
be attributed to correction at all.

VALIDITY CONDITION (prereg section 3.3, unchanged)
--------------------------------------------------
DUMMY_FF is used only if the transpiled circuit provably retains its
conditional blocks. This script checks that before submitting and refuses
if they have been optimised away.

Usage:
    python -m qec.dummyff --dry-run
    python -m qec.dummyff --submit
    python -m qec.dummyff --retrieve runs/dummyff_jobs.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

from qec import tier0, stage_b

PATCHES = [(1, 2, 3, 4, 5), (2, 3, 4, 5, 6), (10, 11, 12, 13, 14)]
SHOTS = 4096
ROUNDS = 3
STATE = 1
JOBS_FILE = "runs/dummyff_jobs.json"


def build_named():
    named = []
    for patch in PATCHES:
        lay = stage_b.layout_for(patch)
        named.append((f"{patch}|ENC_PASSIVE",
                      tier0.build_encoded(ROUNDS, STATE, active=False), lay))
        named.append((f"{patch}|DUMMY_FF",
                      tier0.build_encoded(ROUNDS, STATE, active=True,
                                          dummy_ff=True), lay))
        named.append((f"{patch}|ENC_ACTIVE",
                      tier0.build_encoded(ROUNDS, STATE, active=True), lay))
    return named


def submit():
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    svc = QiskitRuntimeService()
    be = svc.backend("ibm_marrakesh")
    named = build_named()

    cache = {}
    isa = []
    for nm, qc, lay in named:
        t = stage_b.transpile_checked(qc, be, lay, cache)
        n_src = qc.count_ops().get("if_else", 0)
        n_isa = t.count_ops().get("if_else", 0)
        if n_src and n_isa != n_src:
            raise SystemExit(
                f"{nm}: conditionals not preserved ({n_isa}/{n_src}). "
                "DUMMY_FF validity condition fails; do not submit.")
        if "DUMMY_FF" in nm:
            print(f"  {nm}: {n_isa}/{n_src} conditional blocks preserved")
        isa.append(t)

    sampler = SamplerV2(mode=be)
    sampler.options.default_shots = SHOTS
    job = sampler.run(isa)

    stamp = {"patches": [list(p) for p in PATCHES], "shots": SHOTS,
             "rounds": ROUNDS, "state": STATE,
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
    from qec.analyze import enc_pL, wilson
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
            corr = nm.endswith("ENC_PASSIVE")      # offline-decode passive only
            k, n = enc_pL(c, stamp["state"], corr)
            cells[nm] = {"k": k, "n": n, "p_L": k / n,
                         "ci": list(wilson(k, n))}
        except Exception as e:                           # noqa: BLE001
            print(f"  parse failed {nm}: {type(e).__name__}")

    out = {"stamp": stamp, "cells": cells}
    try:
        out["metrics"] = job.metrics().get("usage")
    except Exception:                                    # noqa: BLE001
        pass
    json.dump(out, open("runs/dummyff_result.json", "w"), indent=2)
    print("wrote runs/dummyff_result.json")
    report(out)
    return out


def report(out):
    cells = out["cells"]
    print("\n" + "=" * 74)
    print("E4 ATTRIBUTION — DUMMY_FF (A5 section 3)")
    print(f"ENC_ACTIVE |{out['stamp']['state']}_L>, {out['stamp']['shots']} shots, "
          "all arms in one job")
    print("=" * 74)
    for p in out["stamp"]["patches"]:
        patch = tuple(p)
        pas = cells.get(f"{patch}|ENC_PASSIVE")
        dum = cells.get(f"{patch}|DUMMY_FF")
        act = cells.get(f"{patch}|ENC_ACTIVE")
        if not (pas and dum and act):
            continue
        print(f"\n{patch}")
        for label, c in (("ENC_PASSIVE (offline)", pas),
                         ("DUMMY_FF", dum),
                         ("ENC_ACTIVE", act)):
            print(f"  {label:<24} p_L={c['p_L']:.4f} "
                  f"[{c['ci'][0]:.4f}, {c['ci'][1]:.4f}]")
        cost = dum["p_L"] - pas["p_L"]
        benefit = act["p_L"] - dum["p_L"]
        total = act["p_L"] - pas["p_L"]
        print(f"  {'control-path cost':<24} {cost:+.4f}  "
              f"(DUMMY_FF - PASSIVE)")
        print(f"  {'correction benefit':<24} {benefit:+.4f}  "
              f"(ACTIVE - DUMMY_FF)")
        print(f"  {'net E4 effect':<24} {total:+.4f}  "
              f"(ACTIVE - PASSIVE)")

    print("\n" + "=" * 74)
    print("READING THIS (frozen in A5 section 3)")
    print("=" * 74)
    print("control-path cost near zero AND correction benefit negative")
    print("   -> the E4 advantage is attributable to CORRECTION.")
    print("DUMMY_FF already much better than PASSIVE")
    print("   -> running the conditional structure itself changes the")
    print("      outcome; E4 cannot be attributed to correction.")
    print("Negative p_L differences favour the later arm (lower error).")
    print("=" * 74)
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
        named = build_named()
        print(f"{len(PATCHES)} patches x 3 arms = {len(named)} circuits")
        print(f"{len(named)} x {SHOTS} = {len(named)*SHOTS:,} circuit-shots")
        print(f"projected: {len(named)*SHOTS*3.0/3584:.0f} s")
        print("\narms per patch: ENC_PASSIVE, DUMMY_FF, ENC_ACTIVE")
        d = tier0.build_encoded(ROUNDS, STATE, active=True, dummy_ff=True)
        r = tier0.build_encoded(ROUNDS, STATE, active=True)
        print(f"\nDUMMY_FF if_else blocks (untranspiled): "
              f"{d.count_ops().get('if_else',0)} "
              f"vs ENC_ACTIVE {r.count_ops().get('if_else',0)}")
        print("live-target preservation is checked at submit time")
        print("\nDRY RUN - zero QPU")
        return
    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print("E4 ATTRIBUTION (DUMMY_FF). This SPENDS QPU TIME.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    jf = submit()
    print("waiting (Ctrl+C safe)...")
    time.sleep(5)
    retrieve(jf)


if __name__ == "__main__":
    main()
