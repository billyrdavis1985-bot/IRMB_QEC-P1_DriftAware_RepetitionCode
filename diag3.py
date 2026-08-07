import json, glob
from qec import layouts, tier0
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, thermal_relaxation_error, ReadoutError

snaps=[json.load(open(f)) for f in sorted(glob.glob("data/snapshots/*_converted.json"))]
held=layouts.unique_cycles(snaps)[20]
patch=(1,2,3,16,23); qc=tier0.build_encoded(3,1,active=False)
d1,a1,d2,a2,d3=patch; m={0:d1,1:d2,2:d3,3:a1,4:a2}; pairs=[(0,3),(3,1),(1,4),(4,2)]

def base():
    nm=NoiseModel(basis_gates=["cz","id","rz","sx","x"])
    for sq,pq in m.items():
        p=held["qubits"][str(pq)]; t1=p["T1_us"]*1e-6; t2=min(p["T2_us"]*1e-6,2*t1)
        nm.add_quantum_error(thermal_relaxation_error(t1,t2,60e-9),"x",[sq])
        ro=p.get("readout_error",0.01)
        nm.add_readout_error(ReadoutError([[1-ro,ro],[ro,1-ro]]),[sq])
    return nm

def trial(label, nm):
    print(label,"...",flush=True)
    AerSimulator(noise_model=nm).run(qc,shots=100).result().get_counts()
    print("   OK",flush=True)

nm=base()
for sq,pq in m.items():
    p=held["qubits"][str(pq)]; t1=p["T1_us"]*1e-6; t2=min(p["T2_us"]*1e-6,2*t1)
    nm.add_quantum_error(thermal_relaxation_error(t1,t2,700e-9),"measure",[sq])
trial("A measure-error stacked on readout-error", nm)

nm=base(); cz=held["gates"]["cz"]
for sa,sb in pairs:
    pa,pb=m[sa],m[sb]; g=cz.get("(%d,%d)"%(pa,pb),cz.get("(%d,%d)"%(pb,pa)))
    e=depolarizing_error(g,2)
    nm.add_quantum_error(e,"cz",[sa,sb]); nm.add_quantum_error(e,"cz",[sb,sa])
trial("B cz registered in BOTH directions", nm)

nm=base()
def rel(p):
    q=held["qubits"][str(p)]; t1=q["T1_us"]*1e-6
    return thermal_relaxation_error(t1,min(q["T2_us"]*1e-6,2*t1),84e-9)
for sa,sb in pairs:
    pa,pb=m[sa],m[sb]; g=cz.get("(%d,%d)"%(pa,pb),cz.get("(%d,%d)"%(pb,pa)))
    nm.add_quantum_error(rel(pa).expand(rel(pb)).compose(depolarizing_error(g,2)),"cz",[sa,sb])
trial("C 2q relaxation .expand().compose()", nm)
print("ALL THREE PASSED")
