"""QEC-P1 — patch-score discriminant-validity diagnosis (G4 follow-up).

WHY
---
Tier 1 (2026-08-06, 394/432 cells) returned two findings that must be read
together:

  * the archive policy was consistently WORSE out of sample than the
    current-snapshot policy (positive mean delta in all 6 variant/state
    combinations; archive-better in 1 of 35 paired comparisons), and
  * G4 FAILED: P_weak underperformed in only 48% of comparable cells.

G4 failing is the constraint on interpreting the first finding. If the
patch score cannot reliably tell a bad patch from a good one, then BOTH
policies are argmin over a function that does not predict logical error,
and the archive-vs-today comparison is measuring something murky.

So before concluding anything about longitudinal stability, ask the prior
question: which scoring FEATURES actually predict measured logical error?

WHAT THIS DOES
--------------
Uses the Tier 1 cells already on disk as ground truth. For every
(cycle, policy, variant, class, state) cell with a recorded p_L, it
recomputes the patch's feature values from the held-out snapshot and
correlates each feature -- and the composite score -- against p_L.

Outputs, per envelope variant and logical state:
  * Spearman rank correlation of each feature vs p_L
  * Spearman rank correlation of the COMPOSITE score vs p_L
  * the same for the archive-only temporal terms (variance, tail)

READING THE RESULT
------------------
  composite rho near 0      -> the score has no discriminant validity here;
                               the policy comparison is uninterpretable and
                               the score must be rebuilt before Q-A means
                               anything.
  composite rho strong (+)  -> score is valid (higher score = worse patch =
                               higher p_L); the archive result stands as a
                               genuine negative about temporal weighting.
  individual features split -> re-weight toward the features that predict.

No QPU. No new simulation. Reads runs/tier1_partial.jsonl.

Usage:
    python -m qec.diagnose_score --snapshots "data/snapshots/*_converted.json"
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import defaultdict

from qec import layouts


# ------------------------------------------------------------ statistics --

def _rank(xs: list[float]) -> list[float]:
    """Average ranks, ties shared (needed for a correct Spearman)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation. None when undefined (n<3 or a constant vector)."""
    if len(xs) < 3:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy) ** 0.5


# -------------------------------------------------------------- features --

def patch_features(snap: dict, prior: list[dict],
                   patch: tuple[int, ...]) -> dict[str, float] | None:
    """Per-feature values for one patch, split instantaneous vs temporal.

    Instantaneous terms come from the held-out snapshot (what P_today sees
    one cycle earlier). Temporal terms come from prior history (what only
    P_archive uses). Weight constants mirror qec.layouts so the composite
    below reproduces the deployed score exactly.
    """
    d1, a1, d2, a2, d3 = patch
    qs = [str(q) for q in patch]
    if any(q not in snap.get("qubits", {}) for q in qs):
        return None

    ro = t1inv = t2inv = 0.0
    for q in qs:
        p = snap["qubits"][q]
        if p.get("T1_us") is None or p.get("T2_us") is None:
            return None
        ro += p.get("readout_error", layouts.DEFAULT_READOUT)
        t1inv += 1.0 / max(p["T1_us"], 1.0)
        t2inv += 1.0 / max(p["T2_us"], 1.0)

    cz_sum = 0.0
    for a, b in ((d1, a1), (a1, d2), (d2, a2), (a2, d3)):
        e = layouts.cz_err(snap, a, b)
        if e is None:
            return None
        cz_sum += e

    hist = [layouts.instantaneous_score(s, patch) for s in prior]
    good = [h for h in hist if h is not None]
    if not good:
        return None
    mean_h = statistics.fmean(good)
    var_h = statistics.pstdev(good) if len(good) > 1 else 0.0
    tail_h = max(good) - mean_h
    missing = 1.0 - len(good) / len(hist)

    inst_composite = (layouts.W_READOUT * ro + layouts.W_T1 * t1inv
                      + layouts.W_T2 * t2inv + layouts.W_CZ * cz_sum)
    arch_composite = (mean_h + layouts.W_VAR * var_h
                      + layouts.W_TAIL * tail_h + layouts.W_MISSING * missing)

    return {
        "readout_sum": ro,
        "inv_T1_sum": t1inv,
        "inv_T2_sum": t2inv,
        "cz_err_sum": cz_sum,
        "hist_mean": mean_h,
        "hist_variance": var_h,
        "hist_tail": tail_h,
        "COMPOSITE_today": inst_composite,
        "COMPOSITE_archive": arch_composite,
    }


FEATURES = ["readout_sum", "inv_T1_sum", "inv_T2_sum", "cz_err_sum",
            "hist_mean", "hist_variance", "hist_tail",
            "COMPOSITE_today", "COMPOSITE_archive"]


# ------------------------------------------------------------------ main --

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshots", required=True)
    p.add_argument("--partial", default="runs/tier1_partial.jsonl")
    p.add_argument("--klass", default="ENC_ACTIVE",
                   help="circuit class to diagnose (ENC_ACTIVE/ENC_PASSIVE/BARE)")
    p.add_argument("--json-out", default="runs/score_diagnosis.json")
    a = p.parse_args()

    files = sorted(glob.glob(a.snapshots))
    snaps = [json.load(open(f)) for f in files]
    cycles = layouts.unique_cycles(snaps)

    adj = layouts.coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = layouts.enumerate_patches(adj, alive)

    # rebuild the same policy selections the Tier 1 sweep used
    sel: dict[int, dict[str, tuple]] = {}
    for T in range(2, len(cycles)):
        prior = cycles[:T]
        inst = {q: s for q in patches
                if (s := layouts.instantaneous_score(prior[-1], q)) is not None}
        arch = {q: s for q in patches
                if (s := layouts.archive_score(prior, q)) is not None}
        if inst and arch:
            sel[T] = {"P_today": layouts.rank(inst)[0][0],
                      "P_archive": layouts.rank(arch)[0][0],
                      "P_weak": layouts.rank(inst)[-1][0]}

    rows = []
    for line in open(a.partial):
        d = json.loads(line)
        if d.get("status") != "ok" or d.get("p_L") is None:
            continue
        key = d["key"]
        if not key.startswith("T"):
            continue
        parts = key.split("|")
        if len(parts) != 5:
            continue
        T = int(parts[0][1:]); var, pol, klass, st = parts[1], parts[2], parts[3], int(parts[4])
        if klass != a.klass or T not in sel or pol not in sel[T]:
            continue
        feats = patch_features(cycles[T], cycles[:T], sel[T][pol])
        if feats is None:
            continue
        rows.append({"T": T, "variant": var, "policy": pol, "state": st,
                     "p_L": d["p_L"], **feats})

    print(f"{len(rows)} usable {a.klass} cells from {a.partial}\n")
    if len(rows) < 6:
        raise SystemExit("not enough cells to diagnose")

    groups = defaultdict(list)
    for r in rows:
        groups[(r["variant"], r["state"])].append(r)
    groups["ALL", "ALL"] = rows

    out = {}
    for (var, st), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if len(rs) < 4:
            continue
        pls = [r["p_L"] for r in rs]
        print(f"--- {var} | state {st}  (n={len(rs)}) ---")
        res = {}
        for f in FEATURES:
            rho = spearman([r[f] for r in rs], pls)
            res[f] = rho
            if rho is None:
                print(f"  {f:<20}   n/a")
            else:
                bar = "#" * int(abs(rho) * 20)
                print(f"  {f:<20} {rho:+.3f}  {bar}")
        out[f"{var}|state{st}"] = res
        print()

    allr = out.get("ALL|stateALL", {})
    ct, ca = allr.get("COMPOSITE_today"), allr.get("COMPOSITE_archive")
    print("=" * 68)
    print("DISCRIMINANT VALIDITY VERDICT (pooled)")
    print("=" * 68)
    print("Positive rho = higher score predicts higher logical error,")
    print("which is what a valid 'lower score is better' ranking requires.\n")
    for name, rho in (("instantaneous (P_today) composite", ct),
                      ("archive (P_archive) composite", ca)):
        if rho is None:
            print(f"  {name:<36} undefined")
        else:
            verdict = ("VALID" if rho >= 0.4 else
                       "WEAK" if rho >= 0.2 else
                       "NO DISCRIMINANT VALIDITY")
            print(f"  {name:<36} rho={rho:+.3f}  {verdict}")
    print()
    print("If both composites are near zero, the Tier 1 policy comparison")
    print("cannot be interpreted as being about longitudinal stability --")
    print("it is argmin over a function that does not track logical error.")
    print("Rebuild the score (re-weight toward the features with the")
    print("strongest rho) before Q-A is asked again.")
    print("=" * 68)

    with open(a.json_out, "w") as fh:
        json.dump({"n_rows": len(rows), "klass": a.klass,
                   "correlations": out, "rows": rows}, fh, indent=2)
    print(f"\nwrote {a.json_out}")


if __name__ == "__main__":
    main()
