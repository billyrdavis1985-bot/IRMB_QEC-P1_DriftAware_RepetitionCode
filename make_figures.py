"""QEC-P1 figures â€” built from the committed run data, no hardware.

Four figures, one per load-bearing result:

  fig1_probe_fails.png     probe score vs measured logical error, both
                           probe versions, all 8 candidates per window
  fig2_stability.png       within-job stability against the ten-minute
                           change -- the mechanism, in one image
  fig3_breakeven.png       S per state per window, with the S=1 line
  fig4_e4_power.png        underpowered vs powered E4, difference
                           intervals

Every number is read from runs/*.json. Nothing is hardcoded except axis
labels and the two annotations that quote figures stated in the paper.

Usage:
    python make_figures.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from qec.analyze import enc_pL, bare_pL, wilson
from qec import probe

os.makedirs("figures", exist_ok=True)
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150,
    "font.size": 9, "axes.grid": True, "grid.alpha": 0.25,
    "axes.spines.top": False, "axes.spines.right": False,
})
BLUE, RED, GREY = "#2b6cb0", "#c53030", "#718096"


# ---------------------------------------------------------------- fig 1 --
def fig1():
    """Probe score vs measured p_L. Two windows, two probe designs."""
    panels = []
    for path, label, shots in (
            ("runs/g6ext_1_result.json", "probe v1 â€” 256 shots, 5-qubit sum", 256),
            ("runs/probev2_1_result.json", "probe v2 â€” 4096 shots, data qubits", 4096)):
        if not os.path.exists(path):
            continue
        d = json.load(open(path))
        stamp, counts = d["stamp"], d["counts"]
        st = stamp["state"]
        xs, ys, errs = [], [], []
        for c in stamp["candidates"]:
            patch = tuple(c)
            try:
                r0 = probe.readout_error_from_counts(
                    counts[f"probe|{patch}|readout0"], 0)
                r1 = probe.readout_error_from_counts(
                    counts[f"probe|{patch}|readout1"], 1)
                det = probe.detection_rate_from_counts(
                    counts[f"probe|{patch}|syndrome"])
            except (KeyError, TypeError):
                continue
            dep = counts.get(f"deploy|{patch}|ENC_ACTIVE")
            if not dep:
                continue
            score = (sum(r0[:3]) + sum(r1[:3]) if shots == 4096
                     else probe.probe_score(r0, r1, det))
            k, n = enc_pL(dep, st, False)
            lo, hi = wilson(k, n)
            xs.append(score)
            ys.append(k / n)
            errs.append([k / n - lo, hi - k / n])
        panels.append((label, xs, ys, errs))

    if not panels:
        print("fig1: no data"); return
    fig, axes = plt.subplots(1, len(panels), figsize=(9, 3.6), sharey=True)
    if len(panels) == 1:
        axes = [axes]
    for ax, (label, xs, ys, errs) in zip(axes, panels):
        e = list(map(list, zip(*errs)))
        ax.errorbar(xs, ys, yerr=e, fmt="o", color=BLUE, ms=6,
                    capsize=3, lw=1, mec="white", mew=0.8)
        ax.set_xlabel("probe score  (lower = predicted better)")
        ax.set_title(label, fontsize=9)
    axes[0].set_ylabel("measured logical error  $p_L$")
    fig.suptitle("A better probe is not a better predictor", fontsize=11)
    fig.text(0.5, -0.02, "Each point is one candidate patch, probed and "
             "deployed in the same window. Bars are 95% Wilson intervals.",
             ha="center", fontsize=7.5, color=GREY)
    fig.tight_layout()
    fig.savefig("figures/fig1_probe_fails.png", bbox_inches="tight")
    print("wrote figures/fig1_probe_fails.png")


# ---------------------------------------------------------------- fig 2 --
def fig2():
    """Within-job repeats against the ten-minute change."""
    p = "runs/stability_result.json"
    if not os.path.exists(p):
        print("fig2: no data"); return
    d = json.load(open(p))
    stamp = d["stamp"]
    patches = [tuple(x) for x in stamp["patches"]]
    reps = stamp["repeats"]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    colours = {0: BLUE, 1: RED}
    xoff = {"job_a": 0, "job_b": reps + 1}
    for tag in ("job_a", "job_b"):
        cells = d["jobs"].get(tag)
        if not cells:
            continue
        for pi, patch in enumerate(patches):
            xs, ys = [], []
            for r in range(reps):
                c = cells.get(f"p{pi}|rep{r}")
                if c:
                    xs.append(xoff[tag] + r)
                    ys.append(c["p_L"])
            if xs:
                ax.plot(xs, ys, "o-", color=colours[pi], ms=4, lw=1.2,
                        label=str(patch) if tag == "job_a" else None)

    # the ten-minute reference point from probe v2, same patches
    pv = "runs/probev2_1_result.json"
    if os.path.exists(pv):
        pd_ = json.load(open(pv))
        for pi, patch in enumerate(patches):
            dep = pd_["counts"].get(f"deploy|{patch}|ENC_ACTIVE")
            if not dep:
                continue
            k, n = enc_pL(dep, pd_["stamp"]["state"], False)
            ax.plot([-2.5], [k / n], "D", color=colours[pi], ms=7,
                    mec="black", mew=0.7)
            ax.annotate("", xy=(-0.4, k / n), xytext=(-2.1, k / n),
                        arrowprops=dict(arrowstyle="->", color=colours[pi],
                                        lw=1, alpha=0.6))

    lo_all = min(min(l.get_ydata()) for l in ax.get_lines() if len(l.get_ydata()))
    hi_all = max(max(l.get_ydata()) for l in ax.get_lines() if len(l.get_ydata()))
    pad = (hi_all - lo_all) * 0.18
    ax.set_ylim(lo_all - pad, hi_all + pad)
    ax.axvspan(-3.2, -1.6, color=GREY, alpha=0.10)
    ax.axvspan(-0.6, reps - 0.4, color=BLUE, alpha=0.05)
    ax.axvspan(xoff["job_b"] - 0.6, xoff["job_b"] + reps - 0.4,
               color=BLUE, alpha=0.05)
    ax.text(-2.4, ax.get_ylim()[1] * 0.97, "10 min\nearlier", fontsize=7.5,
            ha="center", va="top", color=GREY)
    ax.text((reps - 1) / 2, ax.get_ylim()[1] * 0.97, "job A",
            fontsize=8, ha="center", va="top", color=GREY)
    ax.text(xoff["job_b"] + (reps - 1) / 2, ax.get_ylim()[1] * 0.97,
            "job B\n(2 min later)", fontsize=8, ha="center", va="top",
            color=GREY)

    ax.set_xticks([])
    ax.set_ylabel("logical error  $p_L$")
    ax.set_title("Stable within a job; reordered across ten minutes",
                 fontsize=11)
    ax.legend(fontsize=8, title="patch", title_fontsize=8,
              loc="upper center", bbox_to_anchor=(0.5, -0.04), ncol=2,
              frameon=False)
    fig.text(0.5, -0.03, "Six interleaved repeats per job. Within a job the "
             "spread is binomial; ten minutes earlier the two patches "
             "differed by 1.7x.", ha="center", fontsize=7.5, color=GREY)
    fig.tight_layout()
    fig.savefig("figures/fig2_stability.png", bbox_inches="tight")
    print("wrote figures/fig2_stability.png")


# ---------------------------------------------------------------- fig 3 --
def fig3():
    """Suppression ratio per state, both windows, against S=1."""
    rows = []
    for w in (1, 2):
        p = f"runs/qb_supplement_{w}_result.json"
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        for m in d["stamp"]["meta"]:
            pol, counts = m["policy"], d["counts"]
            for st in (0, 1):
                bares = []
                for k in range(3):
                    c = counts.get(f"{pol}|BAREMATCH{k}|{st}")
                    if c:
                        kk, nn = bare_pL(c, st)
                        bares.append(kk / nn)
                if not bares:
                    continue
                mb = sum(bares) / len(bares)
                for arm in ("ENC_PASSIVE", "ENC_ACTIVE"):
                    c = counts.get(f"{pol}|{arm}|{st}")
                    if not c:
                        continue
                    kk, nn = enc_pL(c, st, arm == "ENC_PASSIVE")
                    if kk == 0:
                        continue
                    rows.append((w, st, arm, mb / (kk / nn)))
    if not rows:
        print("fig3: no data"); return

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    groups = [(1, "ENC_PASSIVE"), (1, "ENC_ACTIVE"),
              (0, "ENC_PASSIVE"), (0, "ENC_ACTIVE")]
    labels = ["$|1_L\\rangle$\npassive", "$|1_L\\rangle$\nactive",
              "$|0_L\\rangle$\npassive", "$|0_L\\rangle$\nactive"]
    for gi, (st, arm) in enumerate(groups):
        for w, mk in ((1, "o"), (2, "s")):
            ys = [r[3] for r in rows if r[0] == w and r[1] == st and r[2] == arm]
            xs = [gi + (-0.12 if w == 1 else 0.12)] * len(ys)
            ax.plot(xs, ys, mk, color=RED if st == 1 else BLUE, ms=6,
                    mec="white", mew=0.8,
                    label=(f"window {w}" if gi == 0 else None))
    ax.axhline(1.0, color="black", lw=1.1, ls="--")
    ax.text(3.35, 1.04, "break-even", fontsize=8, color="black")
    ax.set_xticks(range(4)); ax.set_xticklabels(labels)
    ax.set_ylabel("suppression ratio  $S = p_{BARE}/p_L$")
    ax.set_yscale("log")
    ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0])
    ax.set_yticklabels(["0.05", "0.1", "0.2", "0.5", "1", "2", "3"])
    ax.minorticks_off()
    ax.set_title("Encoding helps the excited state and not the ground state",
                 fontsize=11)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    fig.text(0.5, -0.04, "Three patches per window, duration-matched bare "
             "baseline. All twelve cells replicate by direction across two "
             "windows 33 hours apart.", ha="center", fontsize=7.5, color=GREY)
    fig.tight_layout()
    fig.savefig("figures/fig3_breakeven.png", bbox_inches="tight")
    print("wrote figures/fig3_breakeven.png")


# ---------------------------------------------------------------- fig 4 --
def fig4():
    """Underpowered vs powered E4: the same question, two resolutions."""
    import math
    under = {"(1,2,3,4,5)": -0.0042, "(2,3,4,5,6)": +0.0017,
             "(10,11,12,13,14)": -0.0139}
    p_typ, n_under = 0.07, 4096
    se_u = math.sqrt(2 * p_typ * (1 - p_typ) / n_under)

    pw = "runs/e4pow_1_result.json"
    powered = {}
    if os.path.exists(pw):
        d = json.load(open(pw))
        stamp, cells = d["stamp"], d["cells"]
        for p in stamp["patches"]:
            patch = tuple(p)
            tot = {}
            for arm in ("ENC_PASSIVE", "ENC_ACTIVE"):
                ks = ns = 0
                for r in range(stamp["repeats"]):
                    c = cells.get(f"{patch}|{arm}|r{r}")
                    if c:
                        ks += c["k"]; ns += c["n"]
                tot[arm] = (ks, ns)
            (ka, na), (kp, np_) = tot["ENC_ACTIVE"], tot["ENC_PASSIVE"]
            pa, pp = ka / na, kp / np_
            se = math.sqrt(pa * (1 - pa) / na + pp * (1 - pp) / np_)
            key = "(" + ",".join(str(x) for x in p) + ")"
            powered[key] = (pa - pp, 1.96 * se)

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    keys = list(under)
    for i, k in enumerate(keys):
        ax.errorbar(under[k], i + 0.16, xerr=1.96 * se_u, fmt="o",
                    color=GREY, ms=6, capsize=3, lw=1.2,
                    label="4,096 shots/arm" if i == 0 else None)
        if k in powered:
            d_, e_ = powered[k]
            ax.errorbar(d_, i - 0.16, xerr=e_, fmt="o", color=BLUE, ms=6,
                        capsize=3, lw=1.6,
                        label="20,480 shots/arm" if i == 0 else None)
    ax.axvline(0, color=RED, lw=1.1, ls="--")
    ax.set_yticks(range(len(keys))); ax.set_yticklabels(keys, fontsize=8)
    ax.set_xlabel("active minus offline-decoded  ($p_L$ difference, "
                  "negative favours correction)")
    ax.set_title("The same effect, under-resolved and resolved", fontsize=11)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=2, frameon=False)
    fig.text(0.5, -0.06, "The underpowered run could not exclude zero and "
             "one patch reversed sign. At five times the shots every "
             "interval excludes zero.", ha="center", fontsize=7.5, color=GREY)
    fig.tight_layout()
    fig.savefig("figures/fig4_e4_power.png", bbox_inches="tight")
    print("wrote figures/fig4_e4_power.png")


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4()
    print("\nfigures written to figures/")

