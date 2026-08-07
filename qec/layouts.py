"""QEC-P1 gate G1 — intervention distinctness between patch-selection policies.

Answers, with ZERO QPU cost, the question that decides whether QEC-P1 can run:

    Do P-archive (rolling longitudinal stability) and P-today (latest
    calibration cycle only) actually select DIFFERENT 5-qubit code patches,
    often enough and with enough score margin to produce informative
    hardware windows?

Per PREREGISTRATION v3 section 7 (G1). Retires the arbitrary 70% threshold
in favour of the functional test: enough disagreement, with enough expected
consequence, to yield >= 2 discordant windows within a 4-window budget.

PATCH TOPOLOGY (d=3 bit-flip repetition code, 5 qubits):

    d1 --- a1 --- d2 --- a2 --- d3

  three data qubits (d1,d2,d3), two syndrome ancillas (a1,a2); a1 measures
  parity of (d1,d2) and a2 of (d2,d3). Each ancilla must be physically
  coupled to BOTH of its data qubits. This is the zero-SWAP requirement:
  the patch is a 5-vertex path in the coupling graph.

POLICIES (both frozen; see prereg 3.2)

  P-today   : instantaneous base-quality terms from the latest eligible
              calibration cycle only. No temporal terms (a single snapshot
              cannot produce variance or tail statistics).
  P-archive : SAME instantaneous terms, PLUS a frozen temporal aggregation
              over every eligible cycle strictly BEFORE the selection point
              (rolling, causal — never uses future information).

Lower score = better patch, matching qnn.rank_snapshots convention.

Usage:
    python qec_g1_convergence.py "exports/*_converted.json"
    python qec_g1_convergence.py "exports/*.json" --budget-windows 4 --top 5
    python qec_g1_convergence.py --self-test
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import defaultdict

# ---------------------------------------------------------------- weights --
# FROZEN at Stage A commit. Instantaneous terms are shared by BOTH policies;
# temporal terms are what makes P-archive a distinct intervention.
# --- Amendment A1 (2026-08-06) -------------------------------------------
# Weights re-derived from measured discriminant validity, not intuition.
# Spearman rho of each feature vs measured logical error, 131 ENC_ACTIVE
# Tier 1 cells:
#     readout_sum +0.607 (dominant; +0.83..+0.91 in EVERY variant/state)
#     cz_err_sum  +0.344   inv_T1_sum +0.306   inv_T2_sum +0.271
#     hist_mean   +0.288
#     hist_variance -0.114  hist_tail -0.188   <-- ANTI-PREDICTIVE
#
# Instantaneous weights are rho-proportional AND scale-corrected, so each
# term's contribution at typical fez values tracks its measured |rho|:
#     readout 6.00 | cz 3.40 | T1 3.02 | T2 2.68
#
# The variance and worst-tail penalties are set to ZERO: they correlated
# negatively with logical error in all six variant/state cells, steering
# selection away from low-readout patches. P-archive is now the historical
# MEAN of the re-weighted instantaneous score -- the one temporal feature
# that predicts in the correct direction.
#
# CIRCULARITY: these weights were derived FROM Tier 1 outcomes. G1 and
# Tier 1 must be re-run from scratch; the old cells are training data, not
# evidence. See PREREGISTRATION.md Amendment A1 section 4.
W_READOUT = 100.0        # readout error, per qubit   (was 1.0)
W_T1 = 115.0             # 1/T1_us, per qubit         (was 50.0)
W_T2 = 75.0              # 1/T2_us, per qubit         (was 50.0)
W_CZ = 327.0             # CZ error per data-ancilla coupler (was 10.0)
W_VAR = 0.0              # RETIRED by A1: rho -0.114, anti-predictive
W_TAIL = 0.0             # RETIRED by A1: rho -0.188, anti-predictive
W_MISSING = 5.0          # ARCHIVE ONLY: fraction of cycles with missing data

DEFAULT_READOUT = 0.01   # fallbacks when a field is absent
DEFAULT_CZ = 0.02
DEFAULT_T = 100.0


# ------------------------------------------------------------ graph utils --
def coupling_from_snapshot(snap: dict) -> dict[int, set[int]]:
    """Undirected adjacency built from the snapshot's CZ keys '(a,b)'."""
    adj: dict[int, set[int]] = defaultdict(set)
    for key in snap.get("gates", {}).get("cz", {}):
        a, b = key.strip("()").split(",")
        a, b = int(a), int(b)
        adj[a].add(b)
        adj[b].add(a)
    return adj


def enumerate_patches(adj: dict[int, set[int]],
                      alive: set[int]) -> list[tuple[int, ...]]:
    """All 5-vertex simple paths d1-a1-d2-a2-d3, canonicalised.

    Returned as (d1, a1, d2, a2, d3). The reversed path is the same physical
    patch, so only one orientation is kept.
    """
    seen: set[tuple[int, ...]] = set()
    out: list[tuple[int, ...]] = []
    for a1 in alive:
        for d1 in adj.get(a1, ()):        # a1's neighbours become data qubits
            if d1 not in alive:
                continue
            for d2 in adj.get(a1, ()):
                if d2 == d1 or d2 not in alive:
                    continue
                for a2 in adj.get(d2, ()):
                    if a2 in (a1, d1) or a2 not in alive:
                        continue
                    for d3 in adj.get(a2, ()):
                        if d3 in (a1, a2, d1, d2) or d3 not in alive:
                            continue
                        patch = (d1, a1, d2, a2, d3)
                        canon = min(patch, patch[::-1])
                        if canon in seen:
                            continue
                        seen.add(canon)
                        out.append(patch)
    return out


# ---------------------------------------------------------------- scoring --
def cz_err(snap: dict, a: int, b: int) -> float | None:
    cz = snap.get("gates", {}).get("cz", {})
    v = cz.get(f"({a},{b})", cz.get(f"({b},{a})"))
    return v


def instantaneous_score(snap: dict, patch: tuple[int, ...]) -> float | None:
    """Shared base-quality term. None if the patch is unscoreable in this cycle.

    patch = (d1, a1, d2, a2, d3); couplers are (d1,a1) (a1,d2) (d2,a2) (a2,d3).
    """
    d1, a1, d2, a2, d3 = patch
    cost = 0.0
    for q in patch:
        qp = snap.get("qubits", {}).get(str(q))
        if qp is None:
            return None
        t1 = qp.get("T1_us")
        t2 = qp.get("T2_us")
        if t1 is None or t2 is None:      # dead qubit (e.g. fez q72 has no T2)
            return None
        cost += W_READOUT * qp.get("readout_error", DEFAULT_READOUT)
        cost += W_T1 / max(t1, 1.0)
        cost += W_T2 / max(t2, 1.0)
    for a, b in ((d1, a1), (a1, d2), (d2, a2), (a2, d3)):
        e = cz_err(snap, a, b)
        if e is None:
            return None                   # coupler absent -> patch invalid
        cost += W_CZ * e
    return cost


def archive_score(history: list[dict], patch: tuple[int, ...]) -> float | None:
    """Rolling temporal aggregation over every cycle in `history`.

    mean + variance penalty + worst-tail penalty + missing-data penalty.
    Causal by construction: the caller passes only prior cycles.
    """
    vals = [instantaneous_score(s, patch) for s in history]
    good = [v for v in vals if v is not None]
    if not good:
        return None
    missing = 1.0 - len(good) / len(vals)
    mean = statistics.fmean(good)
    var = statistics.pstdev(good) if len(good) > 1 else 0.0
    tail = max(good) - mean
    return mean + W_VAR * var + W_TAIL * tail + W_MISSING * missing


def rank(scores: dict[tuple[int, ...], float]) -> list[tuple[tuple[int, ...], float]]:
    return sorted(scores.items(), key=lambda kv: kv[1])


# ------------------------------------------------------------------- main --
def unique_cycles(snaps: list[dict]) -> list[dict]:
    """Collapse to unique calibration cycles.

    Per prereg section 0: the unit of archive analysis is the distinct
    calibration timestamp, NEVER the raw hourly snapshot. Repeated hourly
    pulls of an unchanged calibration are not independent observations.
    """
    by_cal: dict[str, dict] = {}
    for s in snaps:
        key = (s.get("calibration_time")
               or s.get("last_update_date")
               or s.get("timestamp", "?"))
        by_cal.setdefault(str(key), s)     # first pull of each cycle wins
    return [by_cal[k] for k in sorted(by_cal)]


def analyse(snaps: list[dict], budget_windows: int, top_n: int) -> dict:
    cycles = unique_cycles(snaps)
    if len(cycles) < 3:
        raise SystemExit(f"need >=3 unique calibration cycles, got {len(cycles)}")

    adj = coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = enumerate_patches(adj, alive)
    if not patches:
        raise SystemExit("no valid 5-qubit patches found in coupling map")

    rows = []
    # Walk forward. At cycle i, P-archive may use cycles [0, i) only.
    for i in range(1, len(cycles)):
        today = cycles[i]
        history = cycles[:i]

        inst = {p: s for p in patches
                if (s := instantaneous_score(today, p)) is not None}
        arch = {p: s for p in patches
                if (s := archive_score(history, p)) is not None}
        if not inst or not arch:
            continue

        r_today, r_arch = rank(inst), rank(arch)
        p_today, s_today = r_today[0]
        p_arch, s_arch = r_arch[0]

        margin_today = (r_today[1][1] - s_today) if len(r_today) > 1 else float("nan")
        margin_arch = (r_arch[1][1] - s_arch) if len(r_arch) > 1 else float("nan")

        # consequence proxy: how much worse (today) is the archive's pick than
        # today's own pick, measured on TODAY's calibration. 0 when they agree.
        consequence = inst.get(p_arch, float("nan")) - s_today

        rows.append({
            "cycle": str(today.get("calibration_time")
                         or today.get("timestamp", f"#{i}")),
            "p_today": p_today, "p_arch": p_arch,
            "agree": p_today == p_arch,
            "overlap": len(set(p_today) & set(p_arch)),
            "margin_today": margin_today, "margin_arch": margin_arch,
            "consequence": consequence,
            "n_patches": len(inst),
        })

    n = len(rows)
    disc = [r for r in rows if not r["agree"]]
    disagreement_rate = len(disc) / n if n else 0.0
    exp_discordant = disagreement_rate * budget_windows
    cons = [r["consequence"] for r in disc
            if r["consequence"] == r["consequence"]]   # drop NaN

    return {
        "n_cycles": len(cycles), "n_decisions": n,
        "n_patches": len(patches),
        "disagreement_rate": disagreement_rate,
        "expected_discordant_windows": exp_discordant,
        "mean_overlap": statistics.fmean([r["overlap"] for r in rows]) if n else 0,
        "mean_consequence_discordant": statistics.fmean(cons) if cons else 0.0,
        "max_consequence_discordant": max(cons) if cons else 0.0,
        "rows": rows, "top_n": top_n,
    }


def report(res: dict, budget_windows: int, sesoi: float) -> None:
    print(f"\n{'='*68}\nQEC-P1 GATE G1 — INTERVENTION DISTINCTNESS\n{'='*68}")
    print(f"unique calibration cycles : {res['n_cycles']}")
    print(f"valid 5-qubit patches     : {res['n_patches']}")
    print(f"selection decisions       : {res['n_decisions']}")
    print(f"\npolicy disagreement rate  : {res['disagreement_rate']:.1%}")
    print(f"mean qubit overlap        : {res['mean_overlap']:.2f} / 5")
    print(f"expected discordant windows in {budget_windows}: "
          f"{res['expected_discordant_windows']:.1f}")
    print(f"mean score consequence when discordant: "
          f"{res['mean_consequence_discordant']:.5f}")

    print(f"\n{'cycle':<26} {'agree':<6} {'ovl':<4} {'consequence':>12}")
    print("-" * 68)
    for r in res["rows"][-res["top_n"]:]:
        print(f"{r['cycle'][:25]:<26} {str(r['agree']):<6} "
              f"{r['overlap']}/5  {r['consequence']:>12.5f}")

    print(f"\n{'='*68}\nGATE EVALUATION (prereg v3 section 7)\n{'='*68}")
    c1 = res["expected_discordant_windows"] >= 2.0
    print(f"[{'PASS' if c1 else 'FAIL'}] >=2 discordant windows expected "
          f"in a {budget_windows}-window budget "
          f"(got {res['expected_discordant_windows']:.1f})")
    print("[ -- ] expected |delta_pL| >= SESOI/2 "
          f"({sesoi/2:.4f}) during discordance")
    print("       -> requires Tier 1 noisy simulation; the score-space")
    print("          consequence above is a PROXY, not a logical-error delta.")
    print(f"\nDISPOSITION: {'proceed to Tier 1 for the second G1 criterion'
                           if c1 else 'REFRAME per prereg section 9 '
                           '(convergence-dominated)'}")
    print("Neither branch is a failure: convergence is a reportable finding")
    print("about intervention distinctness on this device.\n")


def self_test() -> None:
    """Synthetic archive: a linear chain, one qubit that is good-on-average
    but volatile, so the two policies are forced apart on some cycles."""
    import random
    random.seed(7)
    cycles = []
    for i in range(12):
        qubits, gates = {}, {}
        for q in range(8):
            volatile = (q == 3)
            t1 = 200 + (random.uniform(-90, 90) if volatile else random.uniform(-8, 8))
            qubits[str(q)] = {"T1_us": max(t1, 20.0), "T2_us": max(t1 * 0.8, 15.0),
                              "readout_error": 0.01 + (0.02 if volatile and i % 3 else 0.0)}
        for a in range(7):
            gates[f"({a},{a+1})"] = 0.003 + random.uniform(0, 0.001)
        cycles.append({"calibration_time": f"2026-07-{i+1:02d}T00:00:00Z",
                       "qubits": qubits, "gates": {"cz": gates}})
    res = analyse(cycles, budget_windows=4, top_n=6)
    report(res, 4, 0.010)
    assert res["n_patches"] > 0 and res["n_decisions"] == 11
    print("self-test OK — enumeration, causal history, and gate logic run.\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="*", help="converted snapshot JSON glob(s)")
    p.add_argument("--budget-windows", type=int, default=4)
    p.add_argument("--sesoi", type=float, default=0.010)
    p.add_argument("--top", type=int, default=12)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--json-out", default=None)
    a = p.parse_args()

    if a.self_test:
        self_test()
        return
    if not a.paths:
        raise SystemExit("give snapshot paths, or --self-test")

    files: list[str] = []
    for pattern in a.paths:
        hits = glob.glob(pattern)
        files.extend(hits if hits else [pattern])
    snaps = []
    for f in sorted(files):
        with open(f) as fh:
            snaps.append(json.load(fh))
    print(f"loaded {len(snaps)} snapshot files")

    res = analyse(snaps, a.budget_windows, a.top)
    report(res, a.budget_windows, a.sesoi)

    if a.json_out:
        out = {k: v for k, v in res.items() if k != "rows"}
        out["rows"] = [{**r, "p_today": list(r["p_today"]),
                        "p_arch": list(r["p_arch"])} for r in res["rows"]]
        with open(a.json_out, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"wrote {a.json_out}")


if __name__ == "__main__":
    main()
