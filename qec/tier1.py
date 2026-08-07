"""QEC-P1 Tier 1 (v2) — HELD-OUT archive-seeded simulation and the free gates.

WHAT CHANGED FROM v1, AND WHY IT MATTERED
-----------------------------------------
v1 selected both policies from the archive and then evaluated both against
the noise model of the MOST RECENT snapshot -- the same snapshot P_today
was selected from. P_today was graded on its own answer key, so it won by
construction and the measured gap said nothing about generalisation.

v2 evaluates OUT OF SAMPLE, which is the only design that can distinguish
"longitudinal stability generalises" from "current-snapshot overfits":

    for each held-out cycle T:
        P_today   := argmin instantaneous_score( snapshot[T-1] )
        P_archive := argmin archive_score( snapshots[0 .. T-1] )
        evaluate BOTH on the noise model built from snapshot[T]   <-- held out

Both policies are selected using only information available before T, and
both are judged on a calibration state neither saw. Repeating across many
held-out cycles turns one coin flip into a distribution, which is what the
paired-by-window analysis in the preregistration actually needs.

GATES ANSWERED (prereg v3 sections 6-7)
    G1b : mean |delta p_L| across held-out cycles >= SESOI/2
    G3  : effect >= SESOI under ALL envelope variants (else model uncertainty)
    G4  : does P_weak underperform (discriminant validity)?

Usage:
    python -m qec.tier1 --snapshots "data/snapshots/*_converted.json" --quick
    python -m qec.tier1 --snapshots "..." --holdout 6 --shots 4000
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
import time
from dataclasses import dataclass, asdict

from qec import tier0
from qec import layouts

# ---------------------------------------------------------------- envelope --

@dataclass(frozen=True)
class NoiseVariant:
    """One corner of the G3 envelope: the three channels the archive model
    cannot pin down, bracketed rather than point-estimated (prereg G3)."""
    name: str
    midcircuit_meas_mult: float
    reset_error: float
    feedforward_idle_ns: float


ENVELOPE = (
    NoiseVariant("optimistic",  1.0, 0.002,  300.0),
    NoiseVariant("nominal",     1.5, 0.010,  700.0),
    NoiseVariant("pessimistic", 2.5, 0.030, 1500.0),
)

T_1Q, T_2Q, T_MEAS = 60e-9, 84e-9, 700e-9


# ------------------------------------------------------------ noise model --

def build_patch_noise(snap: dict, patch: tuple[int, ...], var: NoiseVariant):
    """Aer NoiseModel on 5 simulator qubits carrying `patch`'s calibration.

    tier0 register order is d0,d1,d2 then a0,a1; patch is (d1,a1,d2,a2,d3)
    in coupling-path order, so the mapping below is deliberate, not cosmetic.
    """
    from qiskit_aer.noise import (
        NoiseModel, depolarizing_error, thermal_relaxation_error, ReadoutError,
    )
    d1, a1, d2, a2, d3 = patch
    sim_to_phys = {0: d1, 1: d2, 2: d3, 3: a1, 4: a2}
    sim_pairs = [(0, 3), (3, 1), (1, 4), (4, 2)]

    nm = NoiseModel(basis_gates=["cz", "id", "rz", "sx", "x"])
    for sq, pq in sim_to_phys.items():
        props = snap["qubits"].get(str(pq))
        if props is None:
            raise KeyError(f"patch qubit {pq} missing from snapshot")
        t1 = props["T1_us"] * 1e-6
        t2 = min(props["T2_us"] * 1e-6, 2 * t1)

        relax = thermal_relaxation_error(t1, t2, T_1Q)
        for gate in ("sx", "x"):
            g = snap.get("gates", {}).get(gate, {}).get(str(pq))
            nm.add_quantum_error(
                relax.compose(depolarizing_error(g, 1)) if g else relax,
                gate, [sq])

        ro = props.get("readout_error", 0.01)
        is_anc = sq in (3, 4)
        eff = min(ro * (var.midcircuit_meas_mult if is_anc else 1.0), 0.49)
        nm.add_readout_error(ReadoutError([[1 - eff, eff], [eff, 1 - eff]]), [sq])
        nm.add_quantum_error(thermal_relaxation_error(t1, t2, T_MEAS),
                             "measure", [sq])
        if is_anc:
            nm.add_quantum_error(depolarizing_error(var.reset_error, 1),
                                 "reset", [sq])
        if var.feedforward_idle_ns > 0:
            nm.add_quantum_error(
                thermal_relaxation_error(t1, t2, var.feedforward_idle_ns * 1e-9),
                "id", [sq])

    cz = snap.get("gates", {}).get("cz", {})
    for sa, sb in sim_pairs:
        pa, pb = sim_to_phys[sa], sim_to_phys[sb]
        g = cz.get(f"({pa},{pb})", cz.get(f"({pb},{pa})"))
        if g is None:
            raise KeyError(f"coupler ({pa},{pb}) missing")
        def _rel(p):
            q = snap["qubits"][str(p)]
            t1 = q["T1_us"] * 1e-6
            return thermal_relaxation_error(t1, min(q["T2_us"] * 1e-6, 2 * t1), T_2Q)
        err = _rel(pa).expand(_rel(pb)).compose(depolarizing_error(g, 2))
        nm.add_quantum_error(err, "cz", [sa, sb])
        nm.add_quantum_error(err, "cz", [sb, sa])
    return nm


# ------------------------------------------------------------- simulation --

def _p_L_from_counts(counts: dict, active: bool, logical: int) -> float:
    total, fails = sum(counts.values()), 0
    for bitstr, cnt in counts.items():
        f = bitstr.split()
        data_bits = [int(b) for b in f[0][::-1]]
        hist = [(int(x[::-1][0]), int(x[::-1][1])) for x in f[1:][::-1]]
        if tier0.decode_shot(data_bits, hist, apply_corrections=not active) != logical:
            fails += cnt
    return fails / total


def run_condition(snap, patch, var, klass, logical, rounds, shots) -> float:
    from qiskit_aer import AerSimulator
    from qiskit import QuantumCircuit

    sim = AerSimulator(noise_model=build_patch_noise(snap, patch, var))

    if klass == "BARE":
        # Duration-matched memory on the FIRST data qubit (sim qubit 0).
        # Idle count matches the encoded circuit's syndrome structure.
        # NOTE: this is a proxy match; the hardware BARE uses an explicit
        # delay set from the SCHEDULED encoded duration (prereg 3.3), so
        # simulated S values are indicative, not the reportable endpoint.
        qc = QuantumCircuit(5, 1)
        if logical == 1:
            qc.x(0)
        for _ in range(rounds * 4):
            qc.id(0)
        qc.measure(0, 0)
        counts = sim.run(qc, shots=shots).result().get_counts()
        total = sum(counts.values())
        return sum(c for b, c in counts.items() if int(b[-1]) != logical) / total

    active = (klass == "ENC_ACTIVE")
    qc = tier0.build_encoded(rounds, logical, active=active)
    return _p_L_from_counts(sim.run(qc, shots=shots).result().get_counts(),
                            active, logical)


# ------------------------------------------------------- held-out protocol --

def evaluate(snapshots, rounds, shots, sesoi, holdout, quick) -> dict:
    cycles = layouts.unique_cycles(snapshots)
    if len(cycles) < 4:
        raise SystemExit(f"need >=4 unique cycles, got {len(cycles)}")

    adj = layouts.coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = layouts.enumerate_patches(adj, alive)
    print(f"{len(cycles)} unique cycles, {len(patches)} valid patches")

    classes = ["ENC_ACTIVE"] if quick else ["BARE", "ENC_PASSIVE", "ENC_ACTIVE"]
    states = [1] if quick else [0, 1]
    variants = ENVELOPE[1:2] if quick else ENVELOPE

    # held-out cycles: the last `holdout` cycles, each needing >=2 priors
    start = max(2, len(cycles) - holdout)
    test_idx = list(range(start, len(cycles)))
    print(f"held-out evaluation cycles: {len(test_idx)} "
          f"(indices {test_idx[0]}..{test_idx[-1]})\n")

    per_cycle, t0 = [], time.time()
    for n, T in enumerate(test_idx, 1):
        held = cycles[T]                      # <-- NEVER used for selection
        prior = cycles[:T]

        inst = {p: s for p in patches
                if (s := layouts.instantaneous_score(prior[-1], p)) is not None}
        arch = {p: s for p in patches
                if (s := layouts.archive_score(prior, p)) is not None}
        if not inst or not arch:
            continue
        p_today = layouts.rank(inst)[0][0]
        p_arch = layouts.rank(arch)[0][0]
        p_weak = layouts.rank(inst)[-1][0]
        pols = {"P_today": p_today, "P_archive": p_arch, "P_weak": p_weak}

        ts = str(held.get("calibration_time", held.get("timestamp", f"#{T}")))
        agree = p_today == p_arch
        print(f"[{n}/{len(test_idx)}] held-out {ts[:19]}  "
              f"agree={agree}  ({time.time()-t0:.0f}s)")
        sys.stdout.flush()

        cell = {"cycle": ts, "agree": agree,
                "p_today": list(p_today), "p_archive": list(p_arch),
                "p_weak": list(p_weak), "results": {}}
        for var in variants:
            for pol, patch in pols.items():
                for klass in classes:
                    for st in states:
                        try:
                            v = run_condition(held, patch, var, klass, st,
                                              rounds, shots)
                        except KeyError:
                            continue
                        cell["results"][f"{var.name}|{pol}|{klass}|{st}"] = v
        per_cycle.append(cell)

    # ---- aggregate: paired deltas per (variant, state) across cycles -----
    deltas = {}
    for var in variants:
        for st in states:
            vals = []
            for c in per_cycle:
                if c["agree"]:
                    continue              # convergent cycles carry no contrast
                a = c["results"].get(f"{var.name}|P_archive|ENC_ACTIVE|{st}")
                t = c["results"].get(f"{var.name}|P_today|ENC_ACTIVE|{st}")
                if a is not None and t is not None:
                    vals.append(a - t)
            if vals:
                deltas[f"{var.name}|state{st}"] = {
                    "mean": statistics.fmean(vals),
                    "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
                    "n": len(vals),
                    "favours_archive": sum(1 for v in vals if v < 0),
                }

    supp = {}
    for var in variants:
        for st in states:
            rs = []
            for c in per_cycle:
                b = c["results"].get(f"{var.name}|P_archive|BARE|{st}")
                e = c["results"].get(f"{var.name}|P_archive|ENC_ACTIVE|{st}")
                if b is not None and e:
                    rs.append(b / e)
            if rs:
                supp[f"{var.name}|state{st}"] = statistics.fmean(rs)

    weak_flags, weak_distinct_any = [], False
    for c in per_cycle:
        distinct = (c["p_weak"] != c["p_archive"] and c["p_weak"] != c["p_today"])
        weak_distinct_any |= distinct
        if not distinct:
            continue
        for var in variants:
            for st in states:
                w = c["results"].get(f"{var.name}|P_weak|ENC_ACTIVE|{st}")
                a = c["results"].get(f"{var.name}|P_archive|ENC_ACTIVE|{st}")
                t = c["results"].get(f"{var.name}|P_today|ENC_ACTIVE|{st}")
                if None not in (w, a, t):
                    weak_flags.append(w > max(a, t))

    absm = [abs(d["mean"]) for d in deltas.values()]
    return {
        "n_cycles": len(cycles), "n_patches": len(patches),
        "n_heldout": len(per_cycle),
        "n_discordant": sum(1 for c in per_cycle if not c["agree"]),
        "rounds": rounds, "shots": shots, "sesoi": sesoi,
        "per_cycle": per_cycle, "deltas": deltas, "suppression": supp,
        "weak_distinct_any": weak_distinct_any,
        "weak_underperforms_frac": (statistics.fmean(weak_flags)
                                    if weak_flags else None),
        "min_abs_mean_delta": min(absm) if absm else 0.0,
        "max_abs_mean_delta": max(absm) if absm else 0.0,
    }


def report(res: dict) -> None:
    s = res["sesoi"]
    print("\n" + "=" * 72)
    print("TIER 1 (HELD-OUT) GATE EVALUATION — prereg v3 sections 6-7")
    print("=" * 72)
    print(f"held-out cycles evaluated : {res['n_heldout']}")
    print(f"  of which discordant     : {res['n_discordant']}")

    print("\npaired delta p_L on HELD-OUT cycles (archive - today;")
    print("negative favours the archive policy):")
    for k, d in res["deltas"].items():
        print(f"  {k:<26} mean={d['mean']:+.4f}  sd={d['sd']:.4f}  "
              f"n={d['n']}  archive-better in {d['favours_archive']}/{d['n']}")

    if res["suppression"]:
        print("\nmean S = p_BARE / p_ENC_ACTIVE (archive patch, indicative only):")
        for k, v in res["suppression"].items():
            print(f"  {k:<26} S={v:.3f}  "
                  f"{'encoding helps' if v > 1 else 'overhead dominates'}")

    g1b = res["min_abs_mean_delta"] >= s / 2
    print(f"\n[{'PASS' if g1b else 'FAIL'}] G1b: |mean delta| >= SESOI/2 "
          f"({s/2:.4f}); min across envelope = {res['min_abs_mean_delta']:.4f}")
    g3 = res["min_abs_mean_delta"] >= s
    print(f"[{'PASS' if g3 else 'FAIL'}] G3 : effect >= SESOI ({s:.4f}) under ALL "
          f"variants (min = {res['min_abs_mean_delta']:.4f})")
    if not g3 and res["max_abs_mean_delta"] >= s:
        print("       NOTE: variants disagree -> report as MODEL UNCERTAINTY;")
        print("       do not select the favourable variant (prereg G3).")

    wf = res["weak_underperforms_frac"]
    if wf is None:
        print("[ -- ] G4 : NOT EVALUABLE — P_weak never distinct from a policy")
    else:
        print(f"[{'PASS' if wf >= 0.8 else 'FAIL'}] G4 : P_weak underperforms in "
              f"{wf:.0%} of comparable cells (need >=80%)")
        if wf < 0.8:
            print("       -> patch score lacks demonstrated discriminant")
            print("          validity for THIS workload; not automatically")
            print("          simulator error (prereg G4).")

    if res["n_discordant"] == 0:
        print("\nNOTE: zero discordant held-out cycles — the policy question")
        print("is convergence-dominated here (prereg section 9 branch).")

    print("\nDISPOSITION: " + ("proceed to G5 compile gate, then Stage A"
                               if (g1b and g3)
                               else "see prereg section 9 branches"))
    print("=" * 72 + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshots", required=True)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--shots", type=int, default=4000)
    p.add_argument("--sesoi", type=float, default=0.010)
    p.add_argument("--holdout", type=int, default=6,
                   help="number of most-recent cycles to hold out")
    p.add_argument("--quick", action="store_true",
                   help="nominal variant, ENC_ACTIVE, |1_L>, 3 held-out cycles")
    p.add_argument("--json-out", default="runs/tier1_heldout.json")
    a = p.parse_args()

    files = sorted(glob.glob(a.snapshots))
    if not files:
        raise SystemExit(f"no snapshots matched {a.snapshots}")
    snaps = [json.load(open(f)) for f in files]
    holdout = 3 if a.quick else a.holdout
    print(f"loaded {len(snaps)} snapshots | rounds={a.rounds} shots={a.shots} "
          f"holdout={holdout}\n")

    res = evaluate(snaps, a.rounds, a.shots, a.sesoi, holdout, a.quick)
    report(res)
    res["envelope"] = [asdict(v) for v in ENVELOPE]
    with open(a.json_out, "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"wrote {a.json_out}")


if __name__ == "__main__":
    main()
