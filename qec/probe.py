"""QEC-P1 probe module — the P-probe arm (Amendment A2).

WHAT A PROBE IS, AND WHY IT EXISTS
----------------------------------
Tier 1 established, twice, that ranking patches by PASSIVE calibration
metadata (T1/T2/readout/CZ pulled from the API) does not reduce logical
error, and that the score failed discriminant validity (G4) under two
independently derived weightings.

The published method that does work (Ashuraliyev, DAQEC-Benchmark,
Zenodo 10.5281/zenodo.18045662) ranks candidates by MEASURED error from
short probe circuits, then deploys the winner. The difference is
measurement versus proxy. This module implements that difference.

PROBE DESIGN
------------
Two probe circuits per candidate patch, both short and cheap:

  READOUT probe   prepare |0> and |1> on each of the 5 patch qubits,
                  measure immediately. Directly measures state-preparation
                  -and-measurement error per qubit. This is the feature
                  our own Spearman diagnosis found dominant for this
                  workload (rho +0.83..+0.91 in every variant/state cell).

  SYNDROME probe  one round of syndrome extraction on |0_L>, no errors
                  injected. Any nonzero syndrome bit is a false detection
                  event, so its rate measures the combined ancilla,
                  CZ and mid-circuit-measurement quality that a readout
                  probe alone cannot see.

Composite probe score = readout_error_sum + W_SYN * detection_event_rate.
Lower is better, matching layouts.py convention. W_SYN is frozen at
Stage A.

Both probes are STATIC circuits (no if_else), so they avoid the dynamic-
circuit path entirely and are cheap to run: 5 qubits, depth < 10.

BUDGET HONESTY
--------------
The source protocol used 30-shot probes over 9-qubit chains at d=5. Our
patches are d=3, so probe shots and candidate count are NOT inherited --
they are set by our own Stage A cost pilot. The defaults here are
starting points for that pilot, not committed values.

G6 — PROBE VALIDITY GATE (Amendment A2 section 6)
-------------------------------------------------
The same discriminant-validity test that caught the passive score is
applied to the probe. After a session, correlate probe rank against the
measured main-run p_L across candidates. If they are uncorrelated, the
probe has no validity either and Q-A' reports that, exactly as G4
reported it for the passive score. A published positive result elsewhere
is not a licence to skip this check.

Usage:
    python -m qec.probe --demo
    python -m qec.probe --verify
"""
from __future__ import annotations

import argparse

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# Frozen at Stage A. Starting values only until the pilot measures cost.
DEFAULT_PROBE_SHOTS = 256
DEFAULT_N_CANDIDATES = 8
W_SYN = 1.0          # weight on detection-event rate in the probe score


# ------------------------------------------------------------- circuits --

def build_readout_probe(state: int) -> QuantumCircuit:
    """Prepare |state> on all 5 patch qubits and measure immediately.

    Measures SPAM error per qubit. Run for state=0 and state=1: the two
    are not symmetric on superconducting hardware (amplitude damping
    biases 1->0), and the asymmetry itself is informative.
    """
    q = QuantumRegister(5, "q")
    c = ClassicalRegister(5, "m")
    qc = QuantumCircuit(q, c)
    if state == 1:
        for i in range(5):
            qc.x(q[i])
    qc.barrier()
    qc.measure(q, c)
    return qc


def build_syndrome_probe() -> QuantumCircuit:
    """One syndrome round on |0_L>, no injected error.

    In a perfect device every syndrome bit reads 0. Any 1 is a false
    detection event, so the rate directly measures the ancilla + CZ +
    mid-circuit-measurement quality of THIS patch. No if_else, so this
    never touches the dynamic-circuit path.

    Register order matches tier0: d0,d1,d2 then a0,a1.
    """
    d = QuantumRegister(3, "d")
    a = QuantumRegister(2, "a")
    syn = ClassicalRegister(2, "s")
    qc = QuantumCircuit(d, a, syn)
    # |0_L> encoding is trivial (all zeros); go straight to extraction
    qc.cx(d[0], a[0])
    qc.cx(d[1], a[0])
    qc.cx(d[1], a[1])
    qc.cx(d[2], a[1])
    qc.barrier()
    qc.measure(a[0], syn[0])
    qc.measure(a[1], syn[1])
    return qc


# --------------------------------------------------------------- scoring --

def readout_error_from_counts(counts: dict, state: int) -> list[float]:
    """Per-qubit SPAM error from a readout-probe result.

    Returns 5 error rates: the fraction of shots where qubit i did NOT
    read back the prepared state.
    """
    total = sum(counts.values())
    errs = [0.0] * 5
    for bitstr, n in counts.items():
        bits = bitstr.replace(" ", "")[::-1]      # qiskit is little-endian
        for i in range(5):
            if int(bits[i]) != state:
                errs[i] += n
    return [e / total for e in errs]


def detection_rate_from_counts(counts: dict) -> float:
    """Fraction of shots with ANY syndrome bit set on an error-free |0_L>.

    This is the false-detection-event rate for the patch.
    """
    total = sum(counts.values())
    bad = sum(n for b, n in counts.items() if any(ch == "1" for ch in b))
    return bad / total


def probe_score(readout_errs_0: list[float], readout_errs_1: list[float],
                detection_rate: float, w_syn: float = W_SYN) -> float:
    """Composite probe score for one patch. LOWER IS BETTER.

    Both readout directions are summed because amplitude damping makes
    |1> readout worse than |0>, and a patch that is only good in one
    direction is not a good patch.
    """
    return sum(readout_errs_0) + sum(readout_errs_1) + w_syn * detection_rate


def rank_candidates(scores: dict[tuple, float]) -> list[tuple[tuple, float]]:
    return sorted(scores.items(), key=lambda kv: kv[1])


# -------------------------------------------------------------- G6 gate --

def g6_probe_validity(probe_scores: dict[tuple, float],
                      measured_p_L: dict[tuple, float]) -> dict:
    """Does probe rank predict deployed logical error across candidates?

    Same test G4 applied to the passive score. Spearman rank correlation;
    positive means a worse probe score predicts worse measured p_L, which
    is what a valid ranking requires.
    """
    common = [p for p in probe_scores if p in measured_p_L]
    if len(common) < 4:
        return {"n": len(common), "rho": None,
                "verdict": "INSUFFICIENT DATA (need >=4 candidates)"}

    xs = [probe_scores[p] for p in common]
    ys = [measured_p_L[p] for p in common]

    def _rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _rank(xs), _rank(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    rho = None if dx == 0 or dy == 0 else num / (dx * dy) ** 0.5

    if rho is None:
        verdict = "UNDEFINED (constant ranking)"
    elif rho >= 0.4:
        verdict = "PASS - probe has discriminant validity"
    elif rho >= 0.2:
        verdict = "WEAK - report as such, do not claim validity"
    else:
        verdict = "FAIL - probe no better than the passive score was"
    return {"n": len(common), "rho": rho, "verdict": verdict}


# --------------------------------------------------------------- verify --

def verify() -> bool:
    """Tier 0 style checks: the probes must be correct before they cost QPU."""
    from qiskit_aer import AerSimulator
    sim = AerSimulator()
    ok_all = True

    for state in (0, 1):
        qc = build_readout_probe(state)
        counts = sim.run(qc, shots=1000).result().get_counts()
        errs = readout_error_from_counts(counts, state)
        ok = all(e < 1e-9 for e in errs)
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] readout probe |{state}> noiseless "
              f"-> per-qubit error {[round(e,4) for e in errs]}")

    qc = build_syndrome_probe()
    counts = sim.run(qc, shots=1000).result().get_counts()
    rate = detection_rate_from_counts(counts)
    ok = rate < 1e-9
    ok_all &= ok
    print(f"[{'PASS' if ok else 'FAIL'}] syndrome probe noiseless "
          f"-> false-detection rate {rate:.4f} (want 0)")

    # a probe must also RESPOND to noise, or it measures nothing
    from qiskit_aer.noise import NoiseModel, ReadoutError
    nm = NoiseModel(basis_gates=["cz", "id", "rz", "sx", "x"])
    for i in range(5):
        p = 0.02 * (i + 1)                       # graded, q0 best q4 worst
        nm.add_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]), [i])
    noisy = AerSimulator(noise_model=nm)
    counts = noisy.run(build_readout_probe(0), shots=4000).result().get_counts()
    errs = readout_error_from_counts(counts, 0)
    monotone = all(errs[i] < errs[i + 1] for i in range(4))
    ok_all &= monotone
    print(f"[{'PASS' if monotone else 'FAIL'}] readout probe tracks graded noise "
          f"-> {[round(e,4) for e in errs]} (must increase)")

    # G6 self-test: a probe that ranks correctly must PASS, one that is
    # random must FAIL. If the gate cannot fail, it is not a gate.
    good = {(i,): float(i) for i in range(6)}
    truth = {(i,): float(i) * 0.01 for i in range(6)}
    r_good = g6_probe_validity(good, truth)
    bad = {(i,): float([3, 1, 5, 0, 4, 2][i]) for i in range(6)}
    r_bad = g6_probe_validity(bad, truth)
    gate_ok = (r_good["rho"] == 1.0) and (r_bad["rho"] < 0.4)
    ok_all &= gate_ok
    print(f"[{'PASS' if gate_ok else 'FAIL'}] G6 self-test: perfect probe "
          f"rho={r_good['rho']:.2f}, scrambled probe rho={r_bad['rho']:.2f}")

    print("\n" + ("PROBE MODULE VERIFIED" if ok_all else "VERIFICATION FAILED"))
    return ok_all


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        print("--- readout probe |1> ---")
        print(build_readout_probe(1))
        print("\n--- syndrome probe ---")
        print(build_syndrome_probe())
        return
    verify()


if __name__ == "__main__":
    main()
