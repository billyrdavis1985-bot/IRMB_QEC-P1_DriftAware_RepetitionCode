import json, glob
from qec import layouts, tier0
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, thermal_relaxation_error, ReadoutError

snaps=[json.load(open(f)) for f in sorted(glob.glob("data/snapshots/*_converted.json"))]
held=layouts.unique_cycles(snaps)[20]
patch=(1,2,3,16,23); qc=tier0.build_encoded(3,1,active=False)
d1,a1,d2,a2,d3=patch; m={0:d1,1:d2,2:d3,3:a1,4:a2}; pairs=[(0,3),(3,1),(1,4),(4,2)]
cz=held["gates"]["cz"]

nm=NoiseModel(basis_gates=["cz","id","rz","sx","x"])
for sq,pq in m.items():
    p=held["qubits"][str(pq)]; t1=p["T1_us"]*1e-6; t2=min(p["T2_us"]*1e-6,2*t1)
    nm.add_quantum_error(thermal_relaxation_error(t1,t2,60e-9),"x",[sq])
    nm.add_quantum_error(thermal_relaxation_error(t1,t2,60e-9),"sx",[sq])
    ro=p.get("readout_error",0.01)
    nm.add_readout_error(ReadoutError([[1-ro,ro],[ro,1-ro]]),[sq])

# FIX: 2q depolarizing only on cz; per-qubit relaxation for the cz duration
# applied as separate 1q errors instead of one composed 2q channel.
for sa,sb in pairs:
    pa,pb=m[sa],m[sb]
    g=cz.get("(%d,%d)"%(pa,pb),cz.get("(%d,%d)"%(pb,pa)))
    nm.add_quantum_error(depolarizing_error(g,2),"cz",[sa,sb])
    nm.add_quantum_error(depolarizing_error(g,2),"cz",[sb,sa])
for sq,pq in m.items():
    p=held["qubits"][str(pq)]; t1=p["T1_us"]*1e-6; t2=min(p["T2_us"]*1e-6,2*t1)
    nm.add_quantum_error(thermal_relaxation_error(t1,t2,84e-9),"id",[sq])

print("running...",flush=True)
c=AerSimulator(noise_model=nm).run(qc,shots=400).result().get_counts()
print("OK",len(c),"outcomes")

