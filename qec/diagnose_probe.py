"""QEC-P1 — why did the probe fail? Feature diagnosis on the G6 window.

CONTEXT
-------
G6-extended (2026-08-16, window 1) deployed all 8 probed candidates and
found within-session Spearman rho = -0.072 between probe score and
measured ENC_ACTIVE |1_L> logical error. The probe does not predict the
outcome it was built to predict.

That is already a reportable negative. This script asks the follow-up
question that makes it useful rather than merely null: **does ANYTHING
predict p_L for these eight patches?**

HYPOTHESIS UNDER TEST
---------------------
The probe measures SPAM/readout error and syndrome false-detection. It
does NOT measure T1. The Q-B supplement (D-B3) showed |1_L> logical error
is dominated by relaxation across the ~21 us exposure -- bare |1_L> error
0.077-0.235 versus bare |0_L> 0.0005-0.0095.

If relaxation dominates, then T1 on the three DATA qubits (which hold the
state through the whole exposure) should predict p_L, while readout error
should not. The ancilla qubits are measured and reset every round, so
their T1 matters less for state retention.

CAVEAT STATED UP FRONT
----------------------
Archive calibration has been frozen at 2026-08-14 11:04 since before this
window ran, so the archived T1 values are ~2.5 days stale. If stale
archived T1 predicts p_L better than a freshly measured probe does, that
is a striking result -- and it is also a warning that a single window
cannot distinguish "T1 is the right feature" from "these eight patches
happen to line up."

This is EXPLORATORY. It was not pre-declared. It is reported as
hypothesis generation for a probe redesign, never as a confirmatory
finding.

Usage:
    python -m qec.diagnose_probe --window 1
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics

from qec import layouts, probe
from qec.analyze import spearman, enc_pL


def patch_features(snap, patch):
    """Split by role: data qubits hold the state, ancillas are recycled."""
    d1, a1, d2, a2, d3 = patch
    data_q = [str(d1), str(d2), str(d3)]
    anc_q = [str(a1), str(a2)]
    q = snap.get("qubits", {})
    if any(x not in q for x in data_q + anc_q):
        return None

    def grab(keys, field):
        vals = [q[k].get(field) for k in keys]
        return None if any(v is None for v in vals) else vals

    t1_d = grab(data_q, "T1_us")
    t2_d = grab(data_q, "T2_us")
    t1_a = grab(anc_q, "T1_us")
    ro_d = grab(data_q, "readout_error")
    ro_a = grab(anc_q, "readout_error")
    if None in (t1_d, t2_d, t1_a, ro_d, ro_a):
        return None

    cz = 0.0
    for a, b in ((d1, a1), (a1, d2), (d2, a2), (a2, d3)):
        e = layouts.cz_err(snap, a, b)
        if e is None:
            return None
        cz += e

    return {
        "T1_data_min": min(t1_d),
        "T1_data_mean": statistics.fmean(t1_d),
        "inv_T1_data_sum": sum(1.0 / x for x in t1_d),
        "T2_data_min": min(t2_d),
        "inv_T2_data_sum": sum(1.0 / x for x in t2_d),
        "T1_anc_min": min(t1_a),
        "readout_data_sum": sum(ro_d),
        "readout_anc_sum": sum(ro_a),
        "readout_all_sum": sum(ro_d) + sum(ro_a),
        "cz_err_sum": cz,
    }


FEATURES = ["T1_data_min", "T1_data_mean", "inv_T1_data_sum",
            "T2_data_min", "inv_T2_data_sum", "T1_anc_min",
            "readout_data_sum", "readout_anc_sum", "readout_all_sum",
            "cz_err_sum"]

# Sign convention: report rho as measured. For "lower is better" features
# (inverse times, error sums) a POSITIVE rho means the feature predicts
# correctly. For "higher is better" features (raw T1/T2) a NEGATIVE rho
# means it predicts correctly.
HIGHER_IS_BETTER = {"T1_data_min", "T1_data_mean", "T2_data_min", "T1_anc_min"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=1)
    ap.add_argument("--snapshots",
                    default="data/snapshots_marrakesh/*_converted.json")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    res = json.load(open(f"runs/g6ext_{a.window}_result.json"))
    stamp, counts = res["stamp"], res["counts"]
    st = stamp["state"]
    cands = [tuple(c) for c in stamp["candidates"]]

    cycles = layouts.unique_cycles(
        [json.load(open(f)) for f in sorted(glob.glob(a.snapshots))])
    snap = cycles[-1]
    print(f"archive cycle used: {snap.get('calibration_time')}")
    print(f"window {a.window} ran under: {stamp.get('calibration_before')}\n")

    rows = []
    for patch in cands:
        c = counts.get(f"deploy|{patch}|ENC_ACTIVE")
        if not c:
            continue
        k, n = enc_pL(c, st, False)
        f = patch_features(snap, patch)
        if f is None:
            print(f"  {patch}: unscoreable in archive, skipped")
            continue
        # decompose the probe into its parts
        try:
            r0 = probe.readout_error_from_counts(
                counts[f"probe|{patch}|readout0"], 0)
            r1 = probe.readout_error_from_counts(
                counts[f"probe|{patch}|readout1"], 1)
            det = probe.detection_rate_from_counts(
                counts[f"probe|{patch}|syndrome"])
            f["probe_readout_measured"] = sum(r0) + sum(r1)
            f["probe_detection_measured"] = det
            f["probe_score_total"] = probe.probe_score(r0, r1, det)
        except (KeyError, TypeError):
            pass
        f["patch"] = list(patch)
        f["p_L"] = k / n
        rows.append(f)

    if len(rows) < 4:
        raise SystemExit("need >=4 patches with both features and p_L")

    pls = [r["p_L"] for r in rows]
    print(f"{len(rows)} patches, p_L range "
          f"{min(pls):.4f} - {max(pls):.4f}\n")

    print("=" * 72)
    print("FEATURE vs MEASURED p_L  (ENC_ACTIVE |%d_L>)" % st)
    print("=" * 72)
    print(f"{'feature':<26} {'rho':>7}  {'predicts?':<12} bar")
    print("-" * 72)
    results = {}
    order = FEATURES + ["probe_readout_measured", "probe_detection_measured",
                        "probe_score_total"]
    for feat in order:
        if feat not in rows[0]:
            continue
        rho = spearman([r[feat] for r in rows], pls)
        results[feat] = rho
        if rho is None:
            print(f"{feat:<26} {'n/a':>7}")
            continue
        correct = (rho < 0) if feat in HIGHER_IS_BETTER else (rho > 0)
        mag = abs(rho)
        tag = ("predicts" if correct and mag >= 0.4 else
               "weak" if correct and mag >= 0.2 else
               "ANTI" if not correct and mag >= 0.4 else
               "none")
        print(f"{feat:<26} {rho:+7.3f}  {tag:<12} {'#' * int(mag * 20)}")

    print("\n" + "=" * 72)
    print("PER-PATCH DETAIL (sorted by measured p_L)")
    print("=" * 72)
    rows.sort(key=lambda r: r["p_L"])
    print(f"{'patch':<26} {'p_L':>8} {'T1_data_min':>12} "
          f"{'probe':>8} {'cz_sum':>9}")
    for r in rows:
        print(f"{str(tuple(r['patch'])):<26} {r['p_L']:>8.4f} "
              f"{r['T1_data_min']:>12.1f} "
              f"{r.get('probe_score_total', float('nan')):>8.4f} "
              f"{r['cz_err_sum']:>9.5f}")

    print("\n" + "=" * 72)
    print("READING THIS")
    print("=" * 72)
    print("EXPLORATORY, not pre-declared. n=%d patches, one window."
          % len(rows))
    print("A feature that predicts here is a HYPOTHESIS for a probe")
    print("redesign, not a validated selection rule. Confirming it would")
    print("require a fresh pre-declared run on held-out windows.")
    print("Archive calibration is stale (frozen 2026-08-14), so archived")
    print("T1/T2 values do not describe the device as it ran.")
    print("=" * 72)

    if a.json_out:
        json.dump({"window": a.window, "correlations": results,
                   "rows": rows}, open(a.json_out, "w"), indent=2)
        print(f"wrote {a.json_out}")


if __name__ == "__main__":
    main()
