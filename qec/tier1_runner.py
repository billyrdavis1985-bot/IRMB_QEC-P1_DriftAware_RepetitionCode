"""QEC-P1 Tier 1 runner with PROCESS ISOLATION.

WHY THIS EXISTS
---------------
Aer crashes natively (exit -1073741819 / SIGSEGV) partway through a Tier 1
sweep. Established by bisection on 2026-08-05/06:

  * reproduces on Windows AND on Colab Linux -> not OS-specific
  * crashing cycle's calibration values are all physically valid
  * ENC_PASSIVE (no if_else) crashes too -> not the dynamic-circuit path
  * a REUSED simulator crashes on its 2nd run, but the SAME condition
    passes when run first in a fresh process

That last pair is the tell: the fault depends on execution history inside
the process, not on any input. It is memory corruption inside Aer, and it
is not fixable from Python.

So this runner does not try to fix it. Each condition executes in its own
subprocess. A crash kills that one cell, is recorded as "crashed", and the
sweep continues. Results append to disk as they land, so an interrupted or
partially-crashed run keeps everything it earned.

The crash rate is itself reportable: it goes in the Tier 1 deviations entry
with the exit codes, so the record shows exactly which cells are missing
and why.

Usage:
    python -m qec.tier1_runner --snapshots "data/snapshots/*_converted.json"
    python -m qec.tier1_runner --snapshots "..." --holdout 8 --shots 4000
    python -m qec.tier1_runner --resume        # skip cells already on disk
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
import time

# ---------------------------------------------------------------- worker --
# Executed as: python -m qec.tier1_runner --worker <json-spec>
# Prints ONE json line to stdout. Any crash kills only this process.

def _worker(spec: dict) -> None:
    from qec import layouts, tier1
    snaps = [json.load(open(f)) for f in spec["files"]]
    cycles = layouts.unique_cycles(snaps)
    held = cycles[spec["T"]]
    var = next(v for v in tier1.ENVELOPE if v.name == spec["variant"])
    p_L = tier1.run_condition(held, tuple(spec["patch"]), var,
                              spec["klass"], spec["state"],
                              spec["rounds"], spec["shots"])
    print("RESULT " + json.dumps({"key": spec["key"], "p_L": p_L}))


# ------------------------------------------------------------- scheduler --

def plan_cells(files, holdout, quick, rounds, shots):
    """Select policies per held-out cycle and enumerate every condition."""
    from qec import layouts
    snaps = [json.load(open(f)) for f in files]
    cycles = layouts.unique_cycles(snaps)
    if len(cycles) < 4:
        raise SystemExit(f"need >=4 unique cycles, got {len(cycles)}")
    adj = layouts.coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = layouts.enumerate_patches(adj, alive)

    classes = ["ENC_ACTIVE"] if quick else ["BARE", "ENC_PASSIVE", "ENC_ACTIVE"]
    states = [1] if quick else [0, 1]
    variants = ["nominal"] if quick else ["optimistic", "nominal", "pessimistic"]

    start = max(2, len(cycles) - holdout)
    cells, meta = [], []
    for T in range(start, len(cycles)):
        prior = cycles[:T]
        inst = {p: s for p in patches
                if (s := layouts.instantaneous_score(prior[-1], p)) is not None}
        arch = {p: s for p in patches
                if (s := layouts.archive_score(prior, p)) is not None}
        if not inst or not arch:
            continue
        pols = {"P_today": layouts.rank(inst)[0][0],
                "P_archive": layouts.rank(arch)[0][0],
                "P_weak": layouts.rank(inst)[-1][0]}
        held = cycles[T]
        ts = str(held.get("calibration_time", held.get("timestamp", f"#{T}")))
        meta.append({"T": T, "cycle": ts,
                     "agree": pols["P_today"] == pols["P_archive"],
                     **{k: list(v) for k, v in pols.items()}})
        for var in variants:
            for pol, patch in pols.items():
                for klass in classes:
                    for st in states:
                        cells.append({
                            "key": f"T{T}|{var}|{pol}|{klass}|{st}",
                            "T": T, "variant": var, "patch": list(patch),
                            "klass": klass, "state": st,
                            "rounds": rounds, "shots": shots,
                            "files": files,
                        })
    return cells, meta


def run_cell(spec: dict, timeout: int = 900) -> dict:
    """One condition, one process. Never raises on crash."""
    payload = json.dumps(spec)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "qec.tier1_runner", "--worker", payload],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"key": spec["key"], "status": "timeout", "p_L": None}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            d = json.loads(line[7:])
            return {"key": d["key"], "status": "ok", "p_L": d["p_L"]}
    return {"key": spec["key"], "status": "crashed", "p_L": None,
            "exit_code": proc.returncode,
            "stderr_tail": proc.stderr.strip().splitlines()[-1:] or []}


# ------------------------------------------------------------- aggregate --

def aggregate(results: dict, meta: list, sesoi: float) -> dict:
    got = {k: v["p_L"] for k, v in results.items() if v["status"] == "ok"}
    variants = sorted({k.split("|")[1] for k in results})
    states = sorted({int(k.split("|")[4]) for k in results})

    deltas, supp = {}, {}
    for var in variants:
        for st in states:
            vals, ratios = [], []
            for m in meta:
                T = m["T"]
                a = got.get(f"T{T}|{var}|P_archive|ENC_ACTIVE|{st}")
                t = got.get(f"T{T}|{var}|P_today|ENC_ACTIVE|{st}")
                if not m["agree"] and a is not None and t is not None:
                    vals.append(a - t)
                b = got.get(f"T{T}|{var}|P_archive|BARE|{st}")
                if b is not None and a:
                    ratios.append(b / a)
            if vals:
                deltas[f"{var}|state{st}"] = {
                    "mean": statistics.fmean(vals),
                    "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
                    "n": len(vals),
                    "favours_archive": sum(1 for v in vals if v < 0)}
            if ratios:
                supp[f"{var}|state{st}"] = statistics.fmean(ratios)

    weak_flags = []
    for m in meta:
        T = m["T"]
        if m["P_weak"] in (m["P_archive"], m["P_today"]):
            continue
        for var in variants:
            for st in states:
                w = got.get(f"T{T}|{var}|P_weak|ENC_ACTIVE|{st}")
                a = got.get(f"T{T}|{var}|P_archive|ENC_ACTIVE|{st}")
                t = got.get(f"T{T}|{var}|P_today|ENC_ACTIVE|{st}")
                if None not in (w, a, t):
                    weak_flags.append(w > max(a, t))

    absm = [abs(d["mean"]) for d in deltas.values()]
    crashed = [k for k, v in results.items() if v["status"] != "ok"]
    return {
        "n_cells": len(results), "n_ok": len(got), "n_failed": len(crashed),
        "crash_rate": len(crashed) / len(results) if results else 0.0,
        "failed_keys": crashed[:40],
        "meta": meta, "deltas": deltas, "suppression": supp, "sesoi": sesoi,
        "weak_underperforms_frac": (statistics.fmean(weak_flags)
                                    if weak_flags else None),
        "min_abs_mean_delta": min(absm) if absm else 0.0,
        "max_abs_mean_delta": max(absm) if absm else 0.0,
    }


def report(res: dict) -> None:
    s = res["sesoi"]
    print("\n" + "=" * 72)
    print("TIER 1 (HELD-OUT, PROCESS-ISOLATED) GATE EVALUATION")
    print("=" * 72)
    print(f"cells: {res['n_ok']}/{res['n_cells']} ok, "
          f"{res['n_failed']} failed (crash rate {res['crash_rate']:.1%})")
    if res["n_failed"]:
        print("  NOTE: failures are Aer native crashes; they are a logged")
        print("  Tier 1 deviation, not results. Affected keys in the JSON.")

    print("\npaired delta p_L on HELD-OUT cycles (archive - today;")
    print("negative favours the archive policy):")
    for k, d in res["deltas"].items():
        print(f"  {k:<26} mean={d['mean']:+.4f} sd={d['sd']:.4f} n={d['n']} "
              f"archive-better {d['favours_archive']}/{d['n']}")

    if res["suppression"]:
        print("\nmean S = p_BARE / p_ENC_ACTIVE (archive patch, indicative):")
        for k, v in res["suppression"].items():
            print(f"  {k:<26} S={v:.3f}  "
                  f"{'encoding helps' if v > 1 else 'overhead dominates'}")

    g1b = res["min_abs_mean_delta"] >= s / 2
    g3 = res["min_abs_mean_delta"] >= s
    print(f"\n[{'PASS' if g1b else 'FAIL'}] G1b: |mean delta| >= SESOI/2 "
          f"({s/2:.4f}); min = {res['min_abs_mean_delta']:.4f}")
    print(f"[{'PASS' if g3 else 'FAIL'}] G3 : >= SESOI ({s:.4f}) under ALL "
          f"variants; min = {res['min_abs_mean_delta']:.4f}")
    if not g3 and res["max_abs_mean_delta"] >= s:
        print("       variants disagree -> MODEL UNCERTAINTY; do not pick")
        print("       the favourable variant (prereg G3).")

    wf = res["weak_underperforms_frac"]
    if wf is None:
        print("[ -- ] G4 : not evaluable (P_weak never distinct, or no data)")
    else:
        print(f"[{'PASS' if wf >= 0.8 else 'FAIL'}] G4 : P_weak underperforms "
              f"in {wf:.0%} of cells (need >=80%)")

    print("\nDISPOSITION: " + ("proceed to G5 compile gate, then Stage A"
                               if (g1b and g3)
                               else "see prereg section 9 branches"))
    print("=" * 72 + "\n")


# ------------------------------------------------------------------ main --

def main() -> None:
    if "--worker" in sys.argv:
        _worker(json.loads(sys.argv[sys.argv.index("--worker") + 1]))
        return

    p = argparse.ArgumentParser()
    p.add_argument("--snapshots", required=True)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--shots", type=int, default=4000)
    p.add_argument("--sesoi", type=float, default=0.010)
    p.add_argument("--holdout", type=int, default=6)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--resume", action="store_true",
                   help="skip cells already recorded in the partial file")
    p.add_argument("--partial", default="runs/tier1_partial.jsonl")
    p.add_argument("--json-out", default="runs/tier1_heldout.json")
    a = p.parse_args()

    files = sorted(glob.glob(a.snapshots))
    if not files:
        raise SystemExit(f"no snapshots matched {a.snapshots}")
    holdout = 3 if a.quick else a.holdout

    cells, meta = plan_cells(files, holdout, a.quick, a.rounds, a.shots)
    print(f"{len(files)} snapshots | {len(meta)} held-out cycles | "
          f"{len(cells)} cells | shots={a.shots}")
    print(f"discordant cycles: {sum(1 for m in meta if not m['agree'])}"
          f"/{len(meta)}\n")

    os.makedirs(os.path.dirname(a.partial) or ".", exist_ok=True)
    done = {}
    if a.resume and os.path.exists(a.partial):
        for line in open(a.partial):
            d = json.loads(line)
            done[d["key"]] = d
        print(f"resuming: {len(done)} cells already on disk\n")

    t0 = time.time()
    with open(a.partial, "a") as fh:
        for i, spec in enumerate(cells, 1):
            if spec["key"] in done:
                continue
            r = run_cell(spec)
            done[spec["key"]] = r
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            tag = (f"p_L={r['p_L']:.4f}" if r["status"] == "ok"
                   else r["status"].upper())
            print(f"[{i}/{len(cells)}] {spec['key']:<42} {tag} "
                  f"({time.time()-t0:.0f}s)", flush=True)

    res = aggregate(done, meta, a.sesoi)
    report(res)
    with open(a.json_out, "w") as fh:
        json.dump({**res, "cells": done}, fh, indent=2)
    print(f"wrote {a.json_out} (partial log: {a.partial})")


if __name__ == "__main__":
    main()
