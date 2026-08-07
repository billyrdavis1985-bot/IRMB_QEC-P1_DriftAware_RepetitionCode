import json, glob, sys
from qec import layouts, tier1
snaps=[json.load(open(f)) for f in sorted(glob.glob("data/snapshots/*_converted.json"))]
cy=layouts.unique_cycles(snaps)
adj=layouts.coupling_from_snapshot(cy[-1]); alive={int(q) for q in cy[-1]["qubits"]}
pats=layouts.enumerate_patches(adj,alive)
prior=cy[:20]; held=cy[20]
inst={p:s for p in pats if (s:=layouts.instantaneous_score(prior[-1],p)) is not None}
patch=layouts.rank(inst)[0][0]
for i in range(60):
    v=tier1.run_condition(held,patch,tier1.ENVELOPE[1],"ENC_ACTIVE",1,3,300)
    print(i, round(v,4), flush=True)
print("SURVIVED 60")
