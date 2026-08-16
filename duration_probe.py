"""Find a workable duration source for the duration-matched BARE.

Qiskit cannot schedule circuits containing control flow, so ENC_ACTIVE
cannot be scheduled directly. This tries the alternatives in order and
reports what actually works on this Qiskit/backend combination.
"""
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qec import tier0, stage_b
import qiskit

print("qiskit", qiskit.__version__)
svc = QiskitRuntimeService()
be = svc.backend("ibm_marrakesh")
patch = (1, 2, 3, 4, 5)
layout = stage_b.layout_for(patch)

print("\n--- A: schedule ENC_PASSIVE (no control flow) ---")
try:
    pm = generate_preset_pass_manager(optimization_level=3, backend=be,
                                      initial_layout=layout,
                                      scheduling_method="alap")
    s = pm.run(tier0.build_encoded(3, 1, active=False))
    print("  scheduled ok | depth:", s.depth())
    for attr in ("duration", "op_start_times"):
        v = getattr(s, attr, None)
        if attr == "op_start_times" and v:
            print(f"  {attr}: present, last start = {max(v)}")
        else:
            print(f"  {attr}: {v}")
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:150])

print("\n--- B: instruction durations from the target ---")
try:
    t = be.target
    print("  dt =", getattr(t, "dt", None))
    d1, a1, d2, a2, d3 = patch
    for name, key in (("cz", (d1, a1)), ("measure", (a1,)), ("reset", (a1,)),
                      ("x", (d1,)), ("sx", (d1,))):
        try:
            props = t[name][key]
            print(f"  {name}{key}: duration={getattr(props,'duration',None)}")
        except Exception as e:
            print(f"  {name}{key}: unavailable ({type(e).__name__})")
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:150])

print("\n--- C: does ENC_ACTIVE transpile without scheduling? ---")
try:
    pm = generate_preset_pass_manager(optimization_level=3, backend=be,
                                      initial_layout=layout)
    s = pm.run(tier0.build_encoded(3, 1, active=True))
    print("  transpiled ok | depth:", s.depth(),
          "| if_else:", s.count_ops().get("if_else", 0))
    print("  duration attr:", getattr(s, "duration", None))
except Exception as e:
    print("  FAILED:", type(e).__name__, str(e)[:150])
