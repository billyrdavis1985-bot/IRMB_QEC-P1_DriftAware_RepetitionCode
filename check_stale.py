"""Check whether ibm_fez is reporting IBM's documented stale-benchmark marker.

IBM documents: "If the benchmarking of a qubit or edge does not succeed over
the course of several days ... the reported error value is considered stale
and will be reported as 1."

An error value of exactly 1.0 therefore means UNDEFINED, not "broken". If any
patch qubit or coupler reads 1.0, the archive score for that patch is built on
a placeholder and the selection is meaningless for it.
"""
from qiskit_ibm_runtime import QiskitRuntimeService

svc = QiskitRuntimeService()
be = svc.backend("ibm_fez")
props = be.properties(refresh=True)
print("calibration timestamp:", props.last_update_date)

stale_q, stale_e = [], []
for q in range(be.num_qubits):
    try:
        ro = props.readout_error(q)
        if ro is not None and abs(ro - 1.0) < 1e-9:
            stale_q.append(q)
    except Exception:
        pass

for edge in be.coupling_map:
    a, b = tuple(edge)
    for gname in ("cz", "ecr"):
        try:
            g = props.gate_error(gname, [a, b])
            if g is not None and abs(g - 1.0) < 1e-9:
                stale_e.append((gname, a, b))
        except Exception:
            pass

print(f"\nqubits with readout_error == 1.0 (stale/undefined): {len(stale_q)}")
if stale_q:
    print("  ", stale_q[:20])
print(f"couplers with gate_error == 1.0 (stale/undefined): {len(stale_e)}")
if stale_e:
    print("  ", stale_e[:10])

# the patches in play
for name, patch in (("P_probe   ", (3, 16, 23, 22, 21)),
                    ("P_archive ", (141, 142, 143, 144, 145))):
    bad = [q for q in patch if q in stale_q]
    print(f"{name} {patch}: stale qubits -> {bad if bad else 'none'}")
