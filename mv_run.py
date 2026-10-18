"""QEC-P1 multiverse -- confirmatory run. Use ONLY after the multiverse-prereg tag.

    python3 mv_run.py runs/g6ext_1_result.json runs/g6ext_2_result.json runs/g6ext_3_result.json

Primary   : window 2 vs window 3 (fresh, about a day apart)
Secondary : window 1 vs window 2 (two-month separation, reported but not primary)
"""
import json, sys
from multiverse_loader import load_window
import multiverse as mv
try:
    from qec.analyze import enc_pL                 # study decode (WSL / repo)
    SRC = "qec.analyze.enc_pL"
except Exception:
    from frozen_decode import enc_pL               # verbatim fallback
    SRC = "frozen_decode.enc_pL"

ANCHORS = {"10-11-12-13-14": 0.0559, "53-54-55-59-75": 0.1265}   # published G6 values

def cells(path, day):
    return {r["patch_id"]: (r["err"], r["n"]) for r in load_window(path, day, enc_pL_fn=enc_pL)}

def main(w1, w2, w3):
    print(f"decode: {SRC}")
    c1, c2, c3 = cells(w1, 1), cells(w2, 2), cells(w3, 3)
    for p, v in ANCHORS.items():                    # tripwire: decode must match the paper
        got = c1[p][0] / c1[p][1]
        if abs(got - v) > 5e-5:
            raise SystemExit(f"TRIPWIRE: window 1 {p} = {got:.4f}, published {v:.4f}. Stop.")
    print("tripwire passed: window 1 reproduces published anchors")
    assert sorted(c1) == sorted(c2) == sorted(c3), "windows do not contain the same 8 patches"
    out = {}
    for name, a, b in (("primary_W2_vs_W3", c2, c3), ("secondary_W1_vs_W2", c1, c2)):
        s, worlds = mv.run(a, b)
        out[name] = dict(survival=s, band=mv.band(s), worlds=worlds)
        print(f"{name:<22} survival = {s:.3f} over {len(worlds)} worlds -> {mv.band(s)}")
    out["p_L"] = {p: [c[p][0] / c[p][1] for c in (c1, c2, c3)] for p in sorted(c1)}
    out["config"] = mv.CONFIG
    json.dump(out, open("runs/multiverse_result.json", "w"), indent=2)
    print("wrote runs/multiverse_result.json")
    print("Interpretation: 'unstable' here means reshuffling at least as large as a")
    print("+/-0.015 rank-reversing shift. Smaller reshuffles read as stable by design.")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
