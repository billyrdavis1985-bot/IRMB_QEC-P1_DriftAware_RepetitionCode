import json, glob, traceback
from qec import layouts, tier1
snaps=[json.load(open(f)) for f in sorted(glob.glob("data/snapshots/*_converted.json"))]
try:
    res = tier1.evaluate(snaps, 3, 800, 0.010, 3, True)
    print("EVALUATE OK")
    tier1.report(res)
except Exception:
    traceback.print_exc()
