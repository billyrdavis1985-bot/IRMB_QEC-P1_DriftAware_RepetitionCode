"""QEC-P1 final analysis — the frozen analysis model, applied.

Runs only after all sessions are collected. Implements exactly what the
Stage B commit (2026-08-07) and Amendments A2/A3/A4 fixed in advance:

  Q-A' primary   paired within-session risk difference in p_L,
                 ENC_ACTIVE, |1_L>, P_probe minus P_archive.
                 Negative favours the probe. DISCORDANT sessions only —
                 convergent sessions carry no policy contrast.
  Q-A' secondary P_probe vs P_generic, P_archive vs P_generic, both
                 logical states reported separately before averaging.
  Q-B            S = p_BARE / p_L per class per policy. p_BARE from the
                 score-designated best constituent data qubit, and also
                 against the mean of all three.
  Q-C            regress (p_L[P_probe] - p_L[P_generic]) on baseline
                 p_L[P_generic]; x-intercept with bootstrap CI.
                 ESTIMATION ONLY — 4 sessions cannot confirm or refute
                 the published 0.112 crossover.
  E4             p_L(ENC_ACTIVE) vs p_L(ENC_PASSIVE, offline-decoded,
                 all shots) — the fair comparison. A feedforward penalty
                 is ACTIVE > PASSIVE-offline.
  G6             does probe score predict measured p_L?

Postselection is never reported by conditional error alone: acceptance
rate, unconditional success per submitted shot, and QPU-seconds per
successful logical outcome accompany it.

Usage:
    python -m qec.analyze --sessions 11 12 13 14
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics

from qec import tier0

SESOI = 0.010
MAIN_SHOTS = 4096
SESSION_QPU_SECONDS = 40.0      # measured, probe + main


# ------------------------------------------------------------ statistics --

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — the frozen per-cell interval."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            a = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[o[k]] = a
            i = j + 1
        return r
    rx, ry = rk(xs), rk(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    return None if dx == 0 or dy == 0 else num / (dx * dy) ** 0.5


# --------------------------------------------------------------- decoding --

def bare_pL(counts: dict, logical: int) -> tuple[int, int]:
    """BARE is a single 1-bit register: keys are '0'/'1'."""
    n = sum(counts.values())
    k = sum(c for b, c in counts.items() if int(b.strip()[-1]) != logical)
    return k, n


def enc_pL(counts: dict, logical: int, apply_corrections: bool) -> tuple[int, int]:
    """Encoded circuits: 'data s2 s1 s0' with data printed first."""
    n = sum(counts.values())
    k = 0
    for b, c in counts.items():
        f = b.split()
        data_bits = [int(x) for x in f[0][::-1]]
        hist = [(int(x[::-1][0]), int(x[::-1][1])) for x in f[1:][::-1]]
        if tier0.decode_shot(data_bits, hist, apply_corrections) != logical:
            k += c
    return k, n


def postselect(counts: dict, logical: int) -> tuple[int, int, int]:
    """Clean-syndrome rule: reject any shot with a nonzero syndrome bit.

    Returns (failures, accepted, submitted).
    """
    submitted = sum(counts.values())
    acc = fail = 0
    for b, c in counts.items():
        f = b.split()
        if any(ch == "1" for fld in f[1:] for ch in fld):
            continue
        acc += c
        data_bits = [int(x) for x in f[0][::-1]]
        if tier0.decode_shot(data_bits, [], False) != logical:
            fail += c
    return fail, acc, submitted


# ------------------------------------------------------------------ load --

def load(sessions):
    out = {}
    for s in sessions:
        stamp = json.load(open(f"runs/session_{s}_jobs.json"))
        counts = json.load(open(f"runs/session_{s}_counts.json"))["counts"]
        pol = {k: tuple(v) for k, v in stamp["policies"].items()}
        scores = {tuple(json.loads(k)): v
                  for k, v in stamp.get("probe_scores", {}).items()}
        out[s] = {"stamp": stamp, "counts": counts, "policies": pol,
                  "probe_scores": scores,
                  "discordant": pol["P_probe"] != pol["P_archive"],
                  "calibration": stamp.get("calibration_before")}
    return out


def cell(d, pol, klass, state):
    return d["counts"].get(f"{pol}|{klass}|{state}")


# -------------------------------------------------------------- analyses --

def q_a(data, state=1):
    """Primary: paired P_probe - P_archive on ENC_ACTIVE, discordant only."""
    rows = []
    for s, d in sorted(data.items()):
        if not d["discordant"]:
            rows.append({"session": s, "excluded": "convergent"})
            continue
        cp = cell(d, "P_probe", "ENC_ACTIVE", state)
        ca = cell(d, "P_archive", "ENC_ACTIVE", state)
        if not cp or not ca:
            rows.append({"session": s, "excluded": "missing cell"})
            continue
        kp, np_ = enc_pL(cp, state, False)
        ka, na = enc_pL(ca, state, False)
        pp, pa = kp / np_, ka / na
        rows.append({"session": s, "p_probe": pp, "p_archive": pa,
                     "delta": pp - pa,
                     "ci_probe": wilson(kp, np_), "ci_archive": wilson(ka, na),
                     "patch_probe": list(d["policies"]["P_probe"]),
                     "patch_archive": list(d["policies"]["P_archive"])})
    deltas = [r["delta"] for r in rows if "delta" in r]
    summary = None
    if deltas:
        summary = {"n": len(deltas), "mean": statistics.fmean(deltas),
                   "sd": statistics.pstdev(deltas) if len(deltas) > 1 else 0.0,
                   "favours_probe": sum(1 for x in deltas if x < 0),
                   "min": min(deltas), "max": max(deltas)}
    return rows, summary


def q_b(data, state=1):
    """Break-even: S = p_BARE / p_L per policy per class."""
    out = []
    for s, d in sorted(data.items()):
        for pol in ("P_probe", "P_archive", "P_generic"):
            bares = []
            for k in range(3):
                c = cell(d, pol, f"BARE{k}", state)
                if c:
                    kk, nn = bare_pL(c, state)
                    bares.append(kk / nn)
            if not bares:
                continue
            row = {"session": s, "policy": pol,
                   "bare_each": [round(x, 5) for x in bares],
                   "bare_mean": statistics.fmean(bares),
                   "bare_best_measured": min(bares)}
            for klass, corr in (("ENC_PASSIVE", True), ("ENC_ACTIVE", False)):
                c = cell(d, pol, klass, state)
                if not c:
                    continue
                kk, nn = enc_pL(c, state, corr)
                p = kk / nn
                row[klass] = p
                row[klass + "_ci"] = wilson(kk, nn)
                row["S_" + klass] = (row["bare_mean"] / p) if p > 0 else None
            out.append(row)
    return out


def e4(data, state=1):
    """ENC_ACTIVE vs ENC_PASSIVE offline-decoded, all shots — fair comparison."""
    out = []
    for s, d in sorted(data.items()):
        for pol in ("P_probe", "P_archive", "P_generic"):
            ca = cell(d, pol, "ENC_ACTIVE", state)
            cp = cell(d, pol, "ENC_PASSIVE", state)
            if not ca or not cp:
                continue
            ka, na = enc_pL(ca, state, False)
            ko, no = enc_pL(cp, state, True)
            out.append({"session": s, "policy": pol,
                        "active": ka / na, "passive_offline": ko / no,
                        "penalty": ka / na - ko / no})
    return out


def postsel(data, state=1):
    """Postselection with the mandated accompanying quantities."""
    out = []
    for s, d in sorted(data.items()):
        for pol in ("P_probe", "P_archive", "P_generic"):
            c = cell(d, pol, "ENC_PASSIVE", state)
            if not c:
                continue
            f, acc, sub = postselect(c, state)
            if acc == 0:
                continue
            cond = f / acc
            uncond = (acc - f) / sub
            # QPU-seconds per successful logical outcome, from the measured
            # session cost spread over all main-circuit shots
            per_shot = SESSION_QPU_SECONDS / (30 * MAIN_SHOTS)
            out.append({"session": s, "policy": pol,
                        "conditional_pL": cond,
                        "acceptance_rate": acc / sub,
                        "unconditional_success_per_shot": uncond,
                        "qpu_s_per_success": (per_shot / uncond) if uncond else None})
    return out


def g6(data, state=1):
    """Does probe score predict measured p_L? Pooled across sessions."""
    pts = []
    for s, d in sorted(data.items()):
        for pol in ("P_probe", "P_archive"):
            patch = d["policies"][pol]
            score = d["probe_scores"].get(patch)
            c = cell(d, pol, "ENC_ACTIVE", state)
            if score is None or not c:
                continue
            k, n = enc_pL(c, state, False)
            pts.append({"session": s, "policy": pol, "patch": list(patch),
                        "probe_score": score, "p_L": k / n})
    # dedupe convergent sessions (same patch measured once)
    seen, uniq = set(), []
    for p in pts:
        key = (p["session"], tuple(p["patch"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    rho = spearman([p["probe_score"] for p in uniq], [p["p_L"] for p in uniq])
    return uniq, rho


def q_c(data, state=1, n_boot=10000, seed=7):
    """Crossover estimation: regress (probe - generic) on generic baseline."""
    pts = []
    for s, d in sorted(data.items()):
        cg = cell(d, "P_generic", "ENC_ACTIVE", state)
        cp = cell(d, "P_probe", "ENC_ACTIVE", state)
        if not cg or not cp:
            continue
        kg, ng = enc_pL(cg, state, False)
        kp, np_ = enc_pL(cp, state, False)
        pts.append({"session": s, "baseline": kg / ng,
                    "benefit": kp / np_ - kg / ng})
    if len(pts) < 3:
        return pts, None
    xs = [p["baseline"] for p in pts]
    ys = [p["benefit"] for p in pts]

    def fit(x, y):
        mx, my = statistics.fmean(x), statistics.fmean(y)
        den = sum((a - mx) ** 2 for a in x)
        if den == 0:
            return None, None
        b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / den
        return my - b * mx, b

    a, b = fit(xs, ys)
    if b in (None, 0):
        return pts, None
    xint = -a / b
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        idx = [rng.randrange(len(xs)) for _ in xs]
        aa, bb = fit([xs[i] for i in idx], [ys[i] for i in idx])
        if bb not in (None, 0):
            boots.append(-aa / bb)
    boots.sort()
    ci = (boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]) \
        if len(boots) > 40 else None
    return pts, {"slope": b, "intercept": a, "x_intercept": xint,
                 "bootstrap_ci": ci, "n": len(pts)}


# ------------------------------------------------------------------ main --

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", nargs="+", type=int, required=True)
    ap.add_argument("--state", type=int, default=1)
    ap.add_argument("--json-out", default="runs/analysis.json")
    a = ap.parse_args()

    data = load(a.sessions)
    print("=" * 74)
    print("QEC-P1 ANALYSIS — marrakesh, frozen analysis model")
    print("=" * 74)
    for s, d in sorted(data.items()):
        tag = "discordant" if d["discordant"] else "CONVERGENT"
        print(f"  session {s}: {tag:<11} probe={d['policies']['P_probe']} "
              f"archive={d['policies']['P_archive']}")
        print(f"              calibration {d['calibration']}")
    n_disc = sum(1 for d in data.values() if d["discordant"])
    print(f"\n{n_disc} of {len(data)} sessions discordant")
    print("All sessions ran under one frozen calibration cycle ->")
    print("A3 fresh-vs-stale sensitivity analysis NOT EVALUABLE.\n")

    # ---- Q-A' -----------------------------------------------------------
    print("-" * 74)
    print(f"Q-A' PRIMARY — ENC_ACTIVE, |{a.state}_L>, P_probe - P_archive")
    print("negative favours the probe; discordant sessions only")
    print("-" * 74)
    rows, summ = q_a(data, a.state)
    for r in rows:
        if "excluded" in r:
            print(f"  session {r['session']}: excluded ({r['excluded']})")
            continue
        print(f"  session {r['session']}: probe={r['p_probe']:.4f} "
              f"archive={r['p_archive']:.4f}  delta={r['delta']:+.4f}")
        print(f"     probe CI  [{r['ci_probe'][0]:.4f}, {r['ci_probe'][1]:.4f}]"
              f"   archive CI [{r['ci_archive'][0]:.4f}, {r['ci_archive'][1]:.4f}]")
    if summ:
        print(f"\n  paired mean delta = {summ['mean']:+.5f}  "
              f"sd={summ['sd']:.5f}  n={summ['n']}")
        print(f"  probe better in {summ['favours_probe']}/{summ['n']} sessions"
              f"   range [{summ['min']:+.4f}, {summ['max']:+.4f}]")
        print(f"  SESOI = {SESOI}")
        meets = abs(summ["mean"]) >= SESOI
        print(f"  |mean delta| >= SESOI: {meets}")
        print("  INTERPRETATION: pilot estimation. No superiority claim is")
        print("  made at this session count regardless of sign.")

    # ---- G6 -------------------------------------------------------------
    print("\n" + "-" * 74)
    print("G6 — PROBE VALIDITY (does probe score predict measured p_L?)")
    print("-" * 74)
    pts, rho = g6(data, a.state)
    for p in pts:
        print(f"  s{p['session']} {p['policy']:<10} score={p['probe_score']:.5f} "
              f"p_L={p['p_L']:.4f}  {p['patch']}")
    if rho is None:
        print("\n  rho: undefined (insufficient or constant data)")
    else:
        verdict = ("PASS - discriminant validity" if rho >= 0.4 else
                   "WEAK - report as such" if rho >= 0.2 else
                   "FAIL - probe no better than the passive score was")
        print(f"\n  Spearman rho = {rho:+.3f}   {verdict}")
    print("  NOTE: only deployed patches have measured p_L, so this pools")
    print("  across sessions and confounds session-to-session device state.")

    # ---- Q-B ------------------------------------------------------------
    print("\n" + "-" * 74)
    print(f"Q-B — BREAK-EVEN, |{a.state}_L>   S = p_BARE(mean) / p_L")
    print("-" * 74)
    for r in q_b(data, a.state):
        print(f"  s{r['session']} {r['policy']:<10} bare={r['bare_each']} "
              f"mean={r['bare_mean']:.4f}")
        for klass in ("ENC_PASSIVE", "ENC_ACTIVE"):
            if klass in r:
                S = r.get("S_" + klass)
                st = (f"S={S:.3f} " + ("encoding helps" if S and S > 1
                                       else "overhead dominates")) if S else "S=n/a"
                print(f"       {klass:<12} p_L={r[klass]:.4f}  {st}")

    # ---- E4 -------------------------------------------------------------
    print("\n" + "-" * 74)
    print("E4 — FEEDFORWARD: ENC_ACTIVE vs ENC_PASSIVE offline-decoded")
    print("penalty > 0 means active correction performed WORSE")
    print("-" * 74)
    for r in e4(data, a.state):
        print(f"  s{r['session']} {r['policy']:<10} active={r['active']:.4f} "
              f"passive_offline={r['passive_offline']:.4f} "
              f"penalty={r['penalty']:+.4f}")

    # ---- postselection --------------------------------------------------
    print("\n" + "-" * 74)
    print("POSTSELECTION (never reported by conditional error alone)")
    print("-" * 74)
    for r in postsel(data, a.state):
        q = r["qpu_s_per_success"]
        print(f"  s{r['session']} {r['policy']:<10} cond_pL={r['conditional_pL']:.4f} "
              f"accept={r['acceptance_rate']:.3f} "
              f"uncond_success={r['unconditional_success_per_shot']:.4f} "
              f"qpu_s/success={q:.2e}" if q else "")

    # ---- Q-C ------------------------------------------------------------
    print("\n" + "-" * 74)
    print("Q-C — CROSSOVER ESTIMATION (estimation only, not validation)")
    print("-" * 74)
    pts, fitres = q_c(data, a.state)
    for p in pts:
        print(f"  s{p['session']} baseline={p['baseline']:.4f} "
              f"benefit={p['benefit']:+.4f}")
    if fitres:
        ci = fitres["bootstrap_ci"]
        print(f"\n  slope={fitres['slope']:+.3f}  x-intercept="
              f"{fitres['x_intercept']:.4f}")
        if ci:
            print(f"  bootstrap 95% CI [{ci[0]:.4f}, {ci[1]:.4f}]")
        print(f"  n={fitres['n']} sessions — CANNOT confirm or refute the")
        print("  published 0.112 threshold. Reported as an independent")
        print("  point estimate with its uncertainty.")
    else:
        print("  insufficient sessions for a fit (need >=3)")

    print("\n" + "=" * 74)

    out = {"sessions": a.sessions, "state": a.state,
           "q_a_rows": rows, "q_a_summary": summ,
           "g6_points": pts, "g6_rho": rho,
           "q_b": q_b(data, a.state), "e4": e4(data, a.state),
           "postselection": postsel(data, a.state),
           "q_c_points": q_c(data, a.state)[0],
           "q_c_fit": q_c(data, a.state)[1]}
    json.dump(out, open(a.json_out, "w"), indent=2, default=str)
    print(f"wrote {a.json_out}")


if __name__ == "__main__":
    main()
