import json
from qiskit_ibm_runtime import QiskitRuntimeService
from qec import tier0

stamp = json.load(open("runs/stage_a_jobs.json"))
res = QiskitRuntimeService().job(stamp["job_id"]).result()
names = stamp["circuit_names"]
idx = names.index("injected_x_d1")

def joined(pub, regs):
    d = pub.data
    per = {}
    for r in regs:
        try:
            per[r] = d[r].get_bitstrings()      # subscript avoids collision
        except Exception:
            per[r] = getattr(d, r).get_bitstrings()
    out = {}
    for s in range(len(per[regs[0]])):
        k = " ".join(per[r][s] for r in reversed(regs))
        out[k] = out.get(k, 0) + 1
    return out

regs = ["s0", "s1", "s2", "data"]
for nm in ("enc_active_1", "injected_x_d1"):
    c = joined(res[names.index(nm)], regs)
    print(nm, "distinct outcomes:", len(c))
    print("  sample:", list(c)[:3])

c = joined(res[idx], regs)
total = sum(c.values()); fails = 0
for b, n in c.items():
    f = b.split()
    db = [int(x) for x in f[0][::-1]]
    hist = [(int(x[::-1][0]), int(x[::-1][1])) for x in f[1:][::-1]]
    if tier0.decode_shot(db, hist, apply_corrections=False) != 1:
        fails += n
print(f"\ninjected-X logical error = {fails/total:.4f}  corrected={fails/total < 0.5}")
