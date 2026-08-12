import argparse, json, time
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qec import stage_b

ap = argparse.ArgumentParser()
ap.add_argument("--session", type=int, required=True)
ap.add_argument("--wait", action="store_true")
ap.add_argument("--poll", type=int, default=60)
a = ap.parse_args()

jf = "runs/session_%d_jobs.json" % a.session
stamp = json.load(open(jf))
svc = QiskitRuntimeService()

if stamp.get("main_job_id"):
    print("main job already submitted:", svc.job(stamp["main_job_id"]).status())
    print("use: python -m qec.stage_b --retrieve " + jf)
    raise SystemExit

pid = stamp["probe_job_id"]
job = svc.job(pid)
st = str(job.status())
print("probe", pid, st, flush=True)
while "DONE" not in st:
    if "CANCELLED" in st or "ERROR" in st:
        raise SystemExit("probe ended " + st + "; re-run the session")
    if not a.wait:
        print("not finished; re-run with --wait")
        raise SystemExit
    time.sleep(a.poll)
    job = svc.job(pid)
    st = str(job.status())
    print(" ", time.strftime("%H:%M:%S"), st, flush=True)

cands = [tuple(c) for c in stamp["candidates"]]
pn = stage_b.build_probe_set(cands)
pr = job.result()
pc = {}
for i, (nm, qc, _) in enumerate(pn):
    try:
        pc[nm] = stage_b.counts_from_pub(pr[i], qc)
    except Exception:
        pc[nm] = None
scores = stage_b.score_probes(pc, cands)
if not scores:
    raise SystemExit("no usable probe scores")
ranked = sorted(scores.items(), key=lambda kv: kv[1])
p_probe = ranked[0][0]
print("\nprobe ranking (lower is better):")
for p, s in ranked:
    print("  ", str(p).ljust(28), "%.5f" % s, "<- P-probe" if p == p_probe else "")

cycles = stage_b.load_cycles("data/snapshots/*_converted.json")
pol = {"P_probe": p_probe, "P_archive": stage_b.archive_patch(cycles),
       "P_generic": cands[0]}
print("\nP_probe  ", pol["P_probe"])
print("P_archive", pol["P_archive"])

be = svc.backend(stamp["backend"])
mn = stage_b.build_main_set(pol, stamp["seed"])
cache = {}
misa = []
for nm, qc, patch, bi in mn:
    if nm.startswith("P_generic"):
        misa.append(stage_b.transpile_checked(qc, be, None, cache))
    else:
        lay = stage_b.layout_for(patch)
        if bi is not None:
            lay = [lay[bi]]
        misa.append(stage_b.transpile_checked(qc, be, lay, cache))

sm = SamplerV2(mode=be)
sm.options.default_shots = stage_b.MAIN_SHOTS
mj = sm.run(misa)
stamp["main_job_id"] = mj.job_id()
stamp["main_names"] = [n for n, _, _, _ in mn]
stamp["policies"] = {k: list(v) for k, v in pol.items()}
stamp["probe_scores"] = {str(list(k)): v for k, v in scores.items()}
stamp["resumed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
json.dump(stamp, open(jf, "w"), indent=2)
print("\nMAIN job", mj.job_id(), "submitted; saved to", jf)
print("when done: python -m qec.stage_b --retrieve " + jf)
