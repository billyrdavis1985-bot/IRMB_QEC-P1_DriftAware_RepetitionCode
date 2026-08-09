import glob, json
from datetime import datetime
ts = set()
for f in glob.glob("data/snapshots/*_converted.json"):
    s = json.load(open(f))
    t = s.get("calibration_time") or s.get("last_update_date")
    if t: ts.add(str(t))
ds = sorted(datetime.fromisoformat(t) for t in ts)
print(f"{len(ds)} unique calibration cycles")
gaps = [(ds[i+1]-ds[i]).total_seconds()/3600 for i in range(len(ds)-1)]
if gaps:
    print(f"gap hours: min {min(gaps):.1f} | median {sorted(gaps)[len(gaps)//2]:.1f} | max {max(gaps):.1f}")
    print("last cycle in archive:", ds[-1])
