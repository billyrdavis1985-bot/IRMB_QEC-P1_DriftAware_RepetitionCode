"""Did the two-qubit / mid-circuit path degrade after maintenance?

Q-D found every S below 1 on patch (1,2,3,4,5), contradicting Q-B which
found S = 1.49-1.88 on the same patch at the same round count two days
earlier. BARE was comparable across runs; ENC_PASSIVE was ~5x worse.

BARE uses only a delay and a terminal measure. The encoded circuits add
CZ gates, mid-circuit measurement and ancilla reset. So if the device
changed, the change should be visible in the two-qubit and readout
figures for this patch -- not in T1.

This compares the live calibration against the archived cycle the Q-B
windows ran under, for the specific qubits and couplers the circuit uses.

Zero QPU: reads calibration metadata only.

Usage:
    python check_postmaint.py
"""
import glob
import json

from qiskit_ibm_runtime import QiskitRuntimeService

PATCH = (1, 2, 3, 4, 5)          # d1, a1, d2, a2, d3
DATA = [1, 3, 5]                 # d1, d2, d3
ANC = [2, 4]                     # a1, a2
COUPLERS = [(1, 2), (2, 3), (3, 4), (4, 5)]

svc = QiskitRuntimeService()
be = svc.backend("ibm_marrakesh")
props = be.properties(refresh=True)
print("live calibration :", props.last_update_date)

# the archived cycle the Q-B windows scored against
snaps = sorted(glob.glob("data/snapshots_marrakesh/*_converted.json"))
arch = json.load(open(snaps[-1]))
print("archived cycle   :", arch.get("calibration_time"))
print()


def arch_cz(a, b):
    cz = arch.get("gates", {}).get("cz", {})
    return cz.get("(%d,%d)" % (a, b), cz.get("(%d,%d)" % (b, a)))


print("=" * 70)
print("READOUT ERROR — per qubit")
print("=" * 70)
print(f"{'qubit':<8} {'role':<8} {'archived':>10} {'live':>10} {'change':>10}")
for q in PATCH:
    role = "data" if q in DATA else "ancilla"
    a = arch["qubits"].get(str(q), {}).get("readout_error")
    try:
        live = props.readout_error(q)
    except Exception:
        live = None
    if a is None or live is None:
        print(f"{q:<8} {role:<8} {'n/a':>10} {'n/a':>10}")
        continue
    print(f"{q:<8} {role:<8} {a:>10.5f} {live:>10.5f} {(live-a)/a*100:>+9.0f}%")

print("\n" + "=" * 70)
print("CZ ERROR — the four data-ancilla couplers the circuit uses")
print("=" * 70)
print(f"{'coupler':<12} {'archived':>12} {'live':>12} {'change':>10}")
worst = 0.0
for a, b in COUPLERS:
    av = arch_cz(a, b)
    try:
        live = props.gate_error("cz", [a, b])
    except Exception:
        try:
            live = props.gate_error("cz", [b, a])
        except Exception:
            live = None
    if av is None or live is None:
        print(f"{str((a,b)):<12} {'n/a':>12} {'n/a':>12}")
        continue
    ch = (live - av) / av * 100
    worst = max(worst, ch)
    flag = "  <-- degraded" if ch > 50 else ""
    print(f"{str((a,b)):<12} {av:>12.6f} {live:>12.6f} {ch:>+9.0f}%{flag}")

print("\n" + "=" * 70)
print("T1 / T2 — should NOT explain an encoded-only regression")
print("=" * 70)
print(f"{'qubit':<8} {'T1 arch':>9} {'T1 live':>9} {'T2 arch':>9} {'T2 live':>9}")
for q in PATCH:
    a = arch["qubits"].get(str(q), {})
    try:
        t1, t2 = props.t1(q) * 1e6, props.t2(q) * 1e6
    except Exception:
        t1 = t2 = None
    if t1 is None:
        continue
    print(f"{q:<8} {a.get('T1_us', 0):>9.1f} {t1:>9.1f} "
          f"{a.get('T2_us', 0):>9.1f} {t2:>9.1f}")

print("\n" + "=" * 70)
print("READING THIS")
print("=" * 70)
print("Large CZ and/or ancilla-readout degradation with T1/T2 roughly")
print("unchanged would explain an encoded-only regression: BARE touches")
print("neither CZ nor mid-circuit measurement, the encoded circuits use")
print("both heavily (28 two-qubit gates, 9 mid-circuit measurements).")
print()
print("If nothing here moved much, the calibration metadata does NOT")
print("explain the Q-D/Q-B discrepancy -- which would itself be")
print("consistent with this study's central finding that published")
print("calibration figures do not track logical error.")
print("=" * 70)
