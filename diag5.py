import json, glob, traceback
from qec import layouts, tier1, tier0
snaps=[json.load(open(f)) for f in sorted(glob.glob("data/snapshots/*_converted.json"))]
cy=layouts.unique_cycles(snaps)
adj=layouts.coupling_from_snapshot(cy[-1]); alive={int(q) for q in cy[-1]["qubits"]}
pats=layouts.enumerate_patches(adj,alive)
for T in range(18,21):
    prior=cy[:T]; held=cy[T]
    inst={p:s for p in pats if (s:=layouts.instantaneous_score(prior[-1],p)) is not None}
    arch={p:s for p in pats if (s:=layouts.archive_score(prior,p)) is not None}
    pols={"today":layouts.rank(inst)[0][0],"arch":layouts.rank(arch)[0][0],"weak":layouts.rank(inst)[-1][0]}
    for name,patch in pols.items():
        for kl in ("BARE","ENC_PASSIVE","ENC_ACTIVE"):
            for st in (0,1):
                tag="T%d %s %s %s |%d>"%(T,name,str(patch),kl,st)
                try:
                    v=tier1.run_condition(held,patch,tier1.ENVELOPE[1],kl,st,3,300)
                    print(tag,"ok",round(v,4),flush=True)
                except Exception as e:
                    print(tag,"EXCEPTION",type(e).__name__,e,flush=True)
                    traceback.print_exc()
