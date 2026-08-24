"""Extract the Tier 1 per-cell results from the committed Colab notebook.

WHY THIS EXISTS
---------------
The Tier 1 simulation sweeps reported in Section 3 were executed in Google
Colab. The JSON outputs those runs wrote (runs/tier1_heldout.json,
runs/tier1_A1.json, runs/tier1_partial.jsonl, runs/score_diagnosis.json)
were never retrieved from that session before it expired, so they are not
in this repository. That gap is recorded in Section 9 of the paper.

What IS preserved is the notebook itself, with complete console output:
all 432 conditions for both sweeps, every gate evaluation, and the full
feature-correlation table. This script parses that output into a table so
Section 3's numbers can be checked line by line rather than taken on
trust.

WHAT THIS IS NOT
----------------
This is a reconstruction FROM THE CONSOLE LOG, not the original data.

The log reports p_L rounded to four decimal places. The original JSON held
the underlying failure and trial counts, from which p_L was computed at
full precision. A value printed as 0.0080 could be any of several
count pairs. So:

  * aggregate figures recomputed from this table may differ from the
    published ones in the fourth decimal place;
  * this table cannot be used to recompute confidence intervals, which
    need the counts;
  * where this table and the paper disagree, the notebook's own gate
    evaluation output is authoritative, because that was computed from
    the full-precision data at the time.

The honest statement is: Section 3's per-cell values are recoverable and
auditable, its aggregate statistics are preserved verbatim in the
notebook, and its raw count data is not in this repository.

Usage:
    python extract_tier1.py
    python extract_tier1.py --notebook notebooks/IRMB_QEC_P1.ipynb
"""
from __future__ import annotations

import argparse
import csv
import json
import re

# (notebook cell index, sweep label, what it was)
SWEEPS = [
    (16, "tier1_heldout", "original weights, held-out, 8 cycles, 4000 shots"),
    (20, "tier1_A1", "Amendment A1 re-weighted, same protocol"),
]
LINE = re.compile(r"\[(\d+)/(\d+)\]\s+(\S+)\s+(p_L=([\d.]+)|CRASHED|TIMEOUT)")


def cell_text(cell) -> str:
    out = []
    for o in cell.get("outputs", []):
        if "text" in o:
            out.append("".join(o["text"]))
        elif "data" in o and "text/plain" in o["data"]:
            out.append("".join(o["data"]["text/plain"]))
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", default="notebooks/IRMB_QEC_P1.ipynb")
    ap.add_argument("--out", default="runs/tier1_from_notebook.csv")
    a = ap.parse_args()

    nb = json.load(open(a.notebook, encoding="utf-8"))
    rows = []

    for idx, label, note in SWEEPS:
        if idx >= len(nb["cells"]):
            print(f"cell {idx} not present; skipping {label}")
            continue
        text = cell_text(nb["cells"][idx])
        found = LINE.findall(text)
        ok = crashed = 0
        for n, total, key, status, val in found:
            parts = key.split("|")
            if len(parts) != 5:
                continue
            cycle, variant, policy, klass, state = parts
            if status.startswith("p_L"):
                ok += 1
                p_L = float(val)
            else:
                crashed += 1
                p_L = None
            rows.append({
                "sweep": label, "n": int(n), "cycle": cycle,
                "variant": variant, "policy": policy, "class": klass,
                "state": int(state),
                "status": "ok" if p_L is not None else status,
                "p_L": p_L,
            })
        rate = crashed / len(found) * 100 if found else 0
        print(f"{label:<16} {len(found):>3} cells  {ok:>3} ok  "
              f"{crashed:>2} failed  ({rate:.1f}% crash)  — {note}")

    if not rows:
        raise SystemExit("no cell lines parsed; check the notebook path")

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {a.out}  ({len(rows)} rows)")

    # recompute the headline deltas as a cross-check against the paper
    print("\nrecomputed policy deltas (ENC_ACTIVE, archive minus today)")
    print("compare against the notebook's own gate output, which used the")
    print("full-precision counts:\n")
    import statistics
    for label in {r["sweep"] for r in rows}:
        sub = [r for r in rows if r["sweep"] == label and r["status"] == "ok"]
        print(f"  {label}")
        for var in ("optimistic", "nominal", "pessimistic"):
            for st in (0, 1):
                by = {}
                for r in sub:
                    if r["variant"] == var and r["class"] == "ENC_ACTIVE" \
                            and r["state"] == st:
                        by.setdefault(r["cycle"], {})[r["policy"]] = r["p_L"]
                d = [v["P_archive"] - v["P_today"] for v in by.values()
                     if "P_archive" in v and "P_today" in v]
                if d:
                    print(f"    {var:<12} state{st}  mean="
                          f"{statistics.fmean(d):+.4f}  n={len(d)}")
    print("\nDifferences in the fourth decimal are expected: these are")
    print("recomputed from four-decimal log values, not from counts.")


if __name__ == "__main__":
    main()
