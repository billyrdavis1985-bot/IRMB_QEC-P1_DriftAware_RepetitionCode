from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
s = QiskitRuntimeService()
be = s.backend("ibm_fez")
qc = QuantumCircuit(1, 1); qc.x(0); qc.measure(0, 0)
isa = generate_preset_pass_manager(optimization_level=1, backend=be).run(qc)
j = SamplerV2(mode=be).run([isa], shots=10)
print("submitted:", j.job_id())
