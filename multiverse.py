"""QEC-P1 Section 4.3 multiverse -- analysis instrument (pre-freeze).

Question: does the 8-patch ENC_ACTIVE |1_L> logical-error RANKING measured in
one window predict the ranking in a later window? "Effect present" = the
ranking is NOT preserved (instability).

World set (54 worlds) = 3 rank statistics x 2 noise treatments x 9 patch sets
  statistics : spearman (<0.40 unstable), kendall (<0.40), swap_fraction (>=0.25)
  noise      : point estimate | median over binomial bootstrap of both windows
  patch sets : all 8 | 8 leave-one-out sets of 7 (does any single patch drive it?)

Input records: {patch_id, day, state, err, n} per patch per window, as produced
by multiverse_loader.load_window(). Shot counts are taken per cell, so windows
with different shot counts are handled correctly.

Usage:
    python3 multiverse.py --selftest        # controls + detection curve
    python3 multiverse.py --run W2.json W3.json   # confirmatory run (after freeze)
"""
import argparse, itertools, json
import numpy as np

CONFIG = {
    "rho_threshold": 0.40,      # spearman/kendall below this => unstable (G6/A5 threshold)
    "swap_threshold": 0.25,     # >= 25% of patch pairs reordered => unstable
    "n_bootstrap": 2000,
    "placebo_max": 0.10,        # negative control must survive in <= this
    "injected_min": 0.90,       # positive control must survive in >= this ...
    "inject_delta": 0.015,      # ... at this planted drift: the smallest +/- shift that, with ZERO
                                #     shot noise, pushes spearman below 0.40 on the W1 patches
    "overdispersion": 1.42,     # worst observed/binomial SD ratio from Q-E within-job repeats
    "band_robust": 0.85, "band_not_supported": 0.40,
    "seed": 4321,
}
STATS = ["spearman", "kendall", "swap_fraction"]
NOISE = ["point", "bootstrap"]


# ---------------- vectorised statistics (rows = bootstrap draws) ----------------
def _ranks(x):
    return np.argsort(np.argsort(x, axis=-1), axis=-1).astype(float)

def _spearman(a, b):
    ra, rb = _ranks(a), _ranks(b)
    ra -= ra.mean(-1, keepdims=True); rb -= rb.mean(-1, keepdims=True)
    return (ra * rb).sum(-1) / np.sqrt((ra**2).sum(-1) * (rb**2).sum(-1))

def _pair_signs(x):
    i, j = np.triu_indices(x.shape[-1], 1)
    return np.sign(x[..., i] - x[..., j])

def _kendall(a, b):              # tau-a
    return (_pair_signs(a) * _pair_signs(b)).mean(-1)

def _swap(a, b):                 # fraction of pairs whose order flips
    return (_pair_signs(a) * _pair_signs(b) < 0).mean(-1)

FN = {"spearman": _spearman, "kendall": _kendall, "swap_fraction": _swap}

def _unstable(stat, v):
    return v >= CONFIG["swap_threshold"] if stat == "swap_fraction" else v < CONFIG["rho_threshold"]


# ---------------- world enumeration ----------------
def patch_sets(pids):
    sets = [("all", list(pids))]
    sets += [(f"drop:{p}", [q for q in pids if q != p]) for p in pids]
    return sets

def run(day_a, day_b, rng=None, n_boot=None):
    """day_a/day_b: dict patch_id -> (err, n). Returns (survival, worlds)."""
    rng = rng or np.random.default_rng(CONFIG["seed"])
    n_boot = n_boot or CONFIG["n_bootstrap"]
    pids = sorted(day_a)
    assert sorted(day_b) == pids, "both windows must contain the same patches"
    ka = np.array([day_a[p][0] for p in pids]); na = np.array([day_a[p][1] for p in pids])
    kb = np.array([day_b[p][0] for p in pids]); nb = np.array([day_b[p][1] for p in pids])
    pa, pb = ka / na, kb / nb
    ba = rng.binomial(na, pa, size=(n_boot, len(pids))) / na   # shared draws across worlds
    bb = rng.binomial(nb, pb, size=(n_boot, len(pids))) / nb
    idx = {p: i for i, p in enumerate(pids)}
    worlds = []
    for stat, noise, (sname, sub) in itertools.product(STATS, NOISE, patch_sets(pids)):
        cols = [idx[p] for p in sub]
        if noise == "point":
            v = float(FN[stat](pa[cols], pb[cols]))
        else:
            v = float(np.nanmedian(FN[stat](ba[:, cols], bb[:, cols])))
        worlds.append(dict(stat=stat, noise=noise, patches=sname, value=v, unstable=bool(_unstable(stat, v))))
    return float(np.mean([w["unstable"] for w in worlds])), worlds

def band(s):
    if s >= CONFIG["band_robust"]: return "ROBUST"
    if s >= CONFIG["band_not_supported"]: return "FRAGILE"
    return "NOT SUPPORTED"


# ---------------- controls ----------------
def _as_cells(pmap, n):
    return {p: (int(round(v * n)), n) for p, v in pmap.items()}

def placebo_window(base_p, n, rng, overdisp=1.0):
    """Same true rates, fresh shot noise: no drift. overdisp > 1 widens the
    noise to the worst repeat-to-repeat spread measured in Q-E (ratio 1.42)."""
    out = {}
    for p, v in base_p.items():
        q = v
        if overdisp > 1.0:
            extra = np.sqrt(overdisp**2 - 1.0) * np.sqrt(v * (1 - v) / n)
            q = float(np.clip(v + rng.normal(0, extra), 1e-3, 0.4))
        out[p] = (int(rng.binomial(n, q)), n)
    return out

def injected_window(base_p, n, delta, rng):
    """Graded rank-reversing drift: better half up, worse half down, plus shot noise.
    delta=0 is identical to the placebo, so this control cannot pass by construction."""
    order = sorted(base_p, key=base_p.get)
    sign = {p: (1 if i < len(order) / 2 else -1) for i, p in enumerate(order)}
    return {p: (int(rng.binomial(n, float(np.clip(base_p[p] + sign[p] * delta, 1e-3, 0.4)))), n)
            for p in base_p}

def selftest(base_p, n, draws_placebo=200, draws_inject=40, n_boot=300, deltas=(0, .005, .01, .015, .02)):
    rng = np.random.default_rng(CONFIG["seed"])
    out = {"n_shots": n}
    pl = [run(placebo_window(base_p, n, rng), placebo_window(base_p, n, rng), rng, n_boot)[0]
          for _ in range(draws_placebo)]
    out["placebo"] = [float(np.mean(pl)), float(np.std(pl))]
    od = CONFIG["overdispersion"]
    plo = [run(placebo_window(base_p, n, rng, od), placebo_window(base_p, n, rng, od), rng, n_boot)[0]
           for _ in range(draws_placebo)]
    out["placebo_overdispersed"] = [float(np.mean(plo)), float(np.std(plo))]
    curve = {}
    for d in deltas:
        s = [run(placebo_window(base_p, n, rng), injected_window(base_p, n, d, rng), rng, n_boot)[0]
             for _ in range(draws_inject)]
        curve[d] = [float(np.mean(s)), float(np.std(s))]
    out["curve"] = curve
    return out


# validated window-1 vector (reproduced published G6 anchors 0.0559 / 0.1265)
W1_P = {"2-3-4-5-6": 0.0674, "3-4-5-6-7": 0.0645, "1-2-3-4-5": 0.0576, "16-3-4-5-6": 0.0759,
        "10-11-12-13-14": 0.0559, "53-54-55-59-75": 0.1265, "9-10-11-12-13": 0.0884, "8-9-10-11-12": 0.0615}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--run", nargs=2, metavar=("WINDOW_A_RECORDS", "WINDOW_B_RECORDS"))
    a = ap.parse_args()
    if a.selftest:
        r = selftest(W1_P, a.shots, draws_placebo=300, draws_inject=60, n_boot=CONFIG["n_bootstrap"])
        print(json.dumps(r, indent=2))
        pl_ok = max(r["placebo"][0], r["placebo_overdispersed"][0]) <= CONFIG["placebo_max"]
        inj = r["curve"][CONFIG["inject_delta"]][0]
        print(f"placebo {r['placebo'][0]:.3f} (overdispersed {r['placebo_overdispersed'][0]:.3f}) -> {'PASS' if pl_ok else 'FAIL'}; "
              f"injected@{CONFIG['inject_delta']} {inj:.3f} -> {'PASS' if inj >= CONFIG['injected_min'] else 'FAIL'}")
    elif a.run:
        load = lambda f: {r["patch_id"]: (r["err"], r["n"]) for r in json.load(open(f))}
        s, worlds = run(load(a.run[0]), load(a.run[1]))
        print(f"survival = {s:.3f} over {len(worlds)} worlds -> {band(s)}")
        json.dump(dict(survival=s, band=band(s), worlds=worlds, config=CONFIG),
                  open("multiverse_result.json", "w"), indent=2)
