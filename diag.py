import json, glob
snaps=[json.load(open(f)) for f in sorted(glob.glob("data/snapshots/*_converted.json"))]
s=snaps[-1]
for q in (1,2,3,16,23):
    p=s["qubits"][str(q)]
    t1=p["T1_us"]; t2=p["T2_us"]; ro=p.get("readout_error")
    print("q", q, "T1", round(t1,1), "T2", round(t2,1), "ro", ro, "T2>2T1", t2 > 2*t1)
cz=s["gates"]["cz"]
for a,b in ((1,2),(2,3),(3,16),(16,23)):
    print("cz", a, b, cz.get("(%d,%d)"%(a,b), cz.get("(%d,%d)"%(b,a))))
