from qiskit_ibm_runtime import QiskitRuntimeService
s = QiskitRuntimeService()
rows = []
for b in s.backends(operational=True, simulator=False):
    try:
        st = b.status()
        ops = sorted(b.target.operation_names)
        dyn = "if_else" in ops
        rows.append((st.pending_jobs, b.name, b.num_qubits, dyn, st.status_msg))
    except Exception as e:
        rows.append((10**9, b.name, "?", "?", str(e)[:40]))
for p, n, q, d, m in sorted(rows):
    print(f"{n:<18} pending={p:<8} qubits={q:<5} if_else={d}  {m}")
