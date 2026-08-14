from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
s = QiskitRuntimeService()
for name in ("ibm_marrakesh", "ibm_fez"):
    try:
        be = s.backend(name)
        st = be.status()
        print(name, "| operational:", st.operational, "| pending:", st.pending_jobs)
    except Exception as e:
        print(name, "unavailable:", e)
be = s.backend("ibm_marrakesh")
qc = QuantumCircuit(1, 1); qc.x(0); qc.measure(0, 0)
isa = generate_preset_pass_manager(optimization_level=1, backend=be).run(qc)
j = SamplerV2(mode=be).run([isa], shots=10)
print("marrakesh test submitted:", j.job_id())
