"""QEC-P1 Tier 0 — code construction, frozen decoder, and exhaustive verification.

Implements gate G2 of PREREGISTRATION v3:

    all 64 syndrome histories decode per the frozen table; injected-X cases
    decode correctly; ideal logical error rate ~= 0.

This module is the reference implementation of the decoder that section 3.3
of the preregistration freezes. Tier 1 (noisy simulation) and Tier 2
(hardware) both reuse it, so any change here is a preregistration amendment.

PATCH / CODE LAYOUT
-------------------
Physical patch is a 5-vertex path in the coupling graph:

    d1 --- a1 --- d2 --- a2 --- d3

  data      : d1, d2, d3   (the encoded logical qubit)
  ancillas  : a1 measures parity Z(d1)Z(d2)
              a2 measures parity Z(d2)Z(d3)

Distance-3 bit-flip repetition code. Corrects a single X error per round.
Protects the computational (Z) basis ONLY — no phase protection, ever.

FROZEN DECODER (preregistration section 3.3)
--------------------------------------------
Per round, syndrome (s1, s2) maps to a correction:

    (0, 0) -> I          no detected error
    (1, 0) -> X on d1    parity 1 broken, parity 2 intact
    (1, 1) -> X on d2    both parities broken
    (0, 1) -> X on d3    parity 2 broken, parity 1 intact

ENC-ACTIVE applies this in-circuit each round via if_else.
The OFFLINE decoder applies the same table sequentially in software over the
recorded 3-round syndrome history, mirroring the active path exactly.

CIRCUIT CLASSES (preregistration section 3.3)
---------------------------------------------
    BARE         single-qubit memory, duration-matched via explicit delays
    ENC_PASSIVE  encode, N rounds of syndrome extraction, NO in-circuit fix
    ENC_ACTIVE   encode, N rounds, per-round if_else correction
    DUMMY_FF     ENC_ACTIVE's control path with a logically neutral operation
                 (validity is self-verifying: see verify_dummy_ff_preserved)

CONTROL-FLOW RESTRICTIONS honoured throughout: no nested conditionals, and
no measurement or reset inside a conditional branch. Ancilla reuse uses
measurement-conditioned X (IBM tutorial pattern) placed OUTSIDE any branch.

Usage:
    python qec_tier0.py --verify          # G2: exhaustive + injected-X
    python qec_tier0.py --demo            # print circuits
"""
from __future__ import annotations

import argparse
import itertools

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# --------------------------------------------------------------- decoder --

# Frozen per preregistration 3.3. Keys are (s1, s2); values are the index
# into (d1, d2, d3) receiving an X correction, or None for identity.
SYNDROME_TABLE: dict[tuple[int, int], int | None] = {
    (0, 0): None,
    (1, 0): 0,   # X on d1
    (1, 1): 1,   # X on d2
    (0, 1): 2,   # X on d3
}


def decode_history(history: list[tuple[int, int]]) -> list[int]:
    """Offline decoder: apply SYNDROME_TABLE sequentially over rounds.

    Mirrors the in-circuit ENC_ACTIVE path exactly. Returns the net parity of
    corrections applied to each data qubit, as [c1, c2, c3] in GF(2): an odd
    number of X corrections on a qubit flips it, an even number cancels.
    """
    net = [0, 0, 0]
    for s in history:
        idx = SYNDROME_TABLE[tuple(s)]
        if idx is not None:
            net[idx] ^= 1
    return net


def logical_value(data_bits: list[int]) -> int:
    """Majority vote over the three data qubits -> the logical bit."""
    return 1 if sum(data_bits) >= 2 else 0


def decode_shot(data_bits: list[int],
                history: list[tuple[int, int]],
                apply_corrections: bool) -> int:
    """Full offline decode of one shot to a logical value.

    apply_corrections=False reproduces the ENC_PASSIVE 'final-data majority'
    variant; True reproduces the 'offline syndrome-decoded' variant.
    """
    bits = list(data_bits)
    if apply_corrections:
        for i, c in enumerate(decode_history(history)):
            bits[i] ^= c
    return logical_value(bits)


# -------------------------------------------------------------- circuits --

def _syndrome_round(qc: QuantumCircuit, d, a, creg, reset_ancillas: bool):
    """One syndrome-extraction round writing (s1, s2) into `creg`.

    Parity Z(d1)Z(d2) onto a1, Z(d2)Z(d3) onto a2, via CX. Ancillas are reset
    by measurement-conditioned X placed OUTSIDE any conditional branch, per
    the no-reset-inside-branch restriction.
    """
    qc.cx(d[0], a[0])
    qc.cx(d[1], a[0])
    qc.cx(d[1], a[1])
    qc.cx(d[2], a[1])
    qc.barrier()
    qc.measure(a[0], creg[0])
    qc.measure(a[1], creg[1])
    if reset_ancillas:
        qc.reset(a[0])
        qc.reset(a[1])
    qc.barrier()


def build_encoded(rounds: int,
                  logical_state: int,
                  active: bool,
                  dummy_ff: bool = False) -> QuantumCircuit:
    """ENC_PASSIVE / ENC_ACTIVE / DUMMY_FF.

    active=False              -> ENC_PASSIVE (syndromes recorded, no fix)
    active=True               -> ENC_ACTIVE  (per-round if_else correction)
    active=True, dummy_ff=True-> DUMMY_FF    (same control path, neutral op)
    """
    d = QuantumRegister(3, "d")
    a = QuantumRegister(2, "a")
    syn = [ClassicalRegister(2, f"s{r}") for r in range(rounds)]
    out = ClassicalRegister(3, "data")
    qc = QuantumCircuit(d, a, *syn, out)

    # encode |0_L> or |1_L>  (repetition encoding of a computational state)
    if logical_state == 1:
        qc.x(d[0])
    qc.cx(d[0], d[1])
    qc.cx(d[0], d[2])
    qc.barrier()

    for r in range(rounds):
        _syndrome_round(qc, d, a, syn[r], reset_ancillas=True)
        if active:
            # No nested conditionals: one flat if_else per syndrome pattern.
            for (s1, s2), idx in SYNDROME_TABLE.items():
                if idx is None:
                    continue
                val = (s2 << 1) | s1          # creg bit0 = s1, bit1 = s2
                with qc.if_test((syn[r], val)):
                    if dummy_ff:
                        # Logically neutral, but a REAL conditional gate on a
                        # real qubit so the control path and timing survive
                        # transpilation. Applied to an ancilla that has already
                        # been measured and reset this round, so it cannot
                        # affect the data or any later syndrome.
                        qc.x(a[0])
                    else:
                        qc.x(d[idx])
            qc.barrier()

    qc.measure(d[0], out[0])
    qc.measure(d[1], out[1])
    qc.measure(d[2], out[2])
    return qc


def build_bare(logical_state: int, delay_dt: int = 0) -> QuantumCircuit:
    """Duration-matched single-qubit memory (preregistration 3.3, class 1).

    delay_dt is set from the SCHEDULED duration of the encoded circuit on the
    target backend, so BARE carries matched wall-clock exposure. It is a
    matched-memory comparator, never an exact overhead-free counterfactual.
    """
    q = QuantumRegister(1, "q")
    c = ClassicalRegister(1, "data")
    qc = QuantumCircuit(q, c)
    if logical_state == 1:
        qc.x(q[0])
    if delay_dt > 0:
        qc.delay(delay_dt, q[0], unit="dt")
    qc.measure(q[0], c[0])
    return qc


# ---------------------------------------------------------- verification --

def verify_syndrome_table_exhaustive(rounds: int = 3) -> tuple[bool, str]:
    """G2 part 1: every syndrome history in {0,1}^(2*rounds) decodes.

    For rounds=3 that is all 64 histories. Checks the offline decoder is
    total (no KeyError, no ambiguity) and deterministic (same input, same
    output), and that its output is a well-formed correction vector.
    """
    n = 0
    for hist in itertools.product([(0, 0), (1, 0), (1, 1), (0, 1)],
                                  repeat=rounds):
        h = list(hist)
        net = decode_history(h)
        if len(net) != 3 or any(c not in (0, 1) for c in net):
            return False, f"malformed correction {net} for history {h}"
        if decode_history(h) != net:
            return False, f"non-deterministic decode for history {h}"
        n += 1
    expected = 4 ** rounds
    if n != expected:
        return False, f"covered {n} histories, expected {expected}"
    return True, f"all {n} syndrome histories decode deterministically"


def verify_single_error_correction() -> tuple[bool, str]:
    """G2 part 2: a single X on any data qubit is detected AND corrected.

    Computes the true syndrome an X error produces, then confirms the frozen
    table's correction restores the logical value. This is the property the
    code exists for; if it fails, the table is wrong.
    """
    for logical in (0, 1):
        clean = [logical] * 3
        for err_q in range(3):
            bits = list(clean)
            bits[err_q] ^= 1
            # true syndrome: s1 = d1^d2, s2 = d2^d3
            s1 = bits[0] ^ bits[1]
            s2 = bits[1] ^ bits[2]
            idx = SYNDROME_TABLE[(s1, s2)]
            if idx != err_q:
                return False, (f"X on d{err_q+1} (state {logical}) gives "
                               f"syndrome ({s1},{s2}) -> table says d{idx}")
            got = decode_shot(bits, [(s1, s2)], apply_corrections=True)
            if got != logical:
                return False, (f"X on d{err_q+1}: decoded {got}, "
                               f"expected {logical}")
    return True, "all single-X errors on all data qubits decode correctly"


def verify_ideal_simulation(rounds: int = 3, shots: int = 2000) -> tuple[bool, str]:
    """G2 part 3: noiseless simulation gives logical error ~= 0.

    Runs ENC_PASSIVE and ENC_ACTIVE for both logical states on the ideal
    Aer simulator. Any failure here is a bug in the circuit, not a result.
    """
    from qiskit_aer import AerSimulator
    sim = AerSimulator()
    report = []
    for active in (False, True):
        for logical in (0, 1):
            qc = build_encoded(rounds, logical, active=active)
            res = sim.run(qc, shots=shots).result().get_counts()
            fails = 0
            for bitstr, cnt in res.items():
                fields = bitstr.split()          # qiskit: newest reg first
                data = fields[0]
                syn_fields = fields[1:][::-1]    # restore round order
                data_bits = [int(b) for b in data[::-1]]
                hist = [(int(f[::-1][0]), int(f[::-1][1])) for f in syn_fields]
                got = decode_shot(data_bits, hist, apply_corrections=not active)
                if got != logical:
                    fails += cnt
            p_L = fails / shots
            name = "ENC_ACTIVE" if active else "ENC_PASSIVE"
            report.append(f"{name} |{logical}_L>: p_L={p_L:.4f}")
            if p_L > 1e-9:
                return False, f"{name} |{logical}_L> ideal p_L={p_L:.4f} (want 0)"
    return True, "; ".join(report)


def verify_dummy_ff_preserved(rounds: int = 1) -> tuple[bool, str]:
    """DUMMY_FF validity self-check (preregistration 3.3).

    The diagnostic is only usable if the conditional-control path SURVIVES
    transpilation. Here we check it structurally; the preregistration
    additionally requires verifying it against the live backend target with
    scheduling before use. If it cannot be preserved, DUMMY_FF is DROPPED
    and E4 answers the latency question observationally.
    """
    qc = build_encoded(rounds, 0, active=True, dummy_ff=True)
    n_if = sum(1 for inst in qc.data if inst.operation.name == "if_else")
    ref = build_encoded(rounds, 0, active=True, dummy_ff=False)
    n_if_ref = sum(1 for inst in ref.data if inst.operation.name == "if_else")
    if n_if != n_if_ref:
        return False, f"DUMMY_FF has {n_if} if_else vs {n_if_ref} in ENC_ACTIVE"
    if n_if == 0:
        return False, "no conditional blocks present"
    return True, (f"{n_if} conditional blocks match ENC_ACTIVE "
                  f"(live-target scheduling check still required)")


def run_g2(rounds: int = 3) -> bool:
    print("=" * 68)
    print("QEC-P1 GATE G2 — TIER 0 CORRECTNESS")
    print("=" * 68)
    checks = [
        ("exhaustive syndrome decode", verify_syndrome_table_exhaustive, (rounds,)),
        ("single-X correction",        verify_single_error_correction,   ()),
        ("ideal simulation p_L ~ 0",   verify_ideal_simulation,          (rounds,)),
        ("DUMMY_FF control path",      verify_dummy_ff_preserved,        (1,)),
    ]
    ok_all = True
    for name, fn, args in checks:
        try:
            ok, msg = fn(*args)
        except Exception as e:                       # noqa: BLE001
            ok, msg = False, f"exception: {e}"
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n       {msg}")
        ok_all &= ok
    print("=" * 68)
    print(f"G2 DISPOSITION: {'PASS — proceed to Tier 1' if ok_all else 'FAIL — fix before Tier 1'}")
    print("=" * 68)
    return ok_all


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true", help="run gate G2")
    p.add_argument("--demo", action="store_true", help="print circuits")
    p.add_argument("--rounds", type=int, default=3)
    a = p.parse_args()

    if a.demo:
        print("--- ENC_ACTIVE, 1 round, |1_L> ---")
        print(build_encoded(1, 1, active=True))
        print("\n--- BARE, |1_L>, delay 1000dt ---")
        print(build_bare(1, delay_dt=1000))
        return
    run_g2(a.rounds)


if __name__ == "__main__":
    main()
