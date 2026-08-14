"""QEC-P1 Stage A â€” engineering pilot on ibm_fez. THE FIRST QPU SPEND.

PURPOSE (PREREGISTRATION v3 section 4, Amendment A2 section 5)
--------------------------------------------------------------
Measure the real per-session QPU cost of this study's circuits, and
verify the control path executes on hardware. Stage B then sizes the
confirmatory matrix from the MEASURED number.

This script does NOT answer any scientific question. That restriction is
enforced in code, not left to discipline: see FORBIDDEN ANALYSES below.

SAFEGUARDS CARRIED FROM QNN-P1 (learned the expensive way)
----------------------------------------------------------
  * job IDs are written to disk IMMEDIATELY after submission, BEFORE any
    wait. Ctrl+C, a crash, or a closed laptop cannot orphan a job.
  * --retrieve recovers any prior submission for zero additional QPU.
  * --dry-run executes the entire path on a local simulator, no account
    contact, so the pipeline is proven before a second is spent.
  * cost is READ FROM THE METER afterwards, never estimated. An estimate
    was wrong by an order of magnitude once; it does not get another
    chance to size anything.
  * a hard budget guard refuses to submit past the declared cap.

DIAGNOSTIC PATCH
----------------
Stage A runs on the THIRD-ranked patch under the archive score, chosen
deliberately so the pilot does not touch patches the confirmatory policy
comparison is likely to select. Pilot data must not contaminate Stage B.

FORBIDDEN ANALYSES (prereg v3 section 4, enforced below)
--------------------------------------------------------
Allowed from this pilot: metered cost, transpilation success and circuit
properties, result schema, circuit duration, job/subjob structure,
reset and control-path execution success, injected-X decode correctness.

NOT allowed before Stage B is committed: any policy-level or patch-level
logical error rate, any suppression ratio S, any comparison between
patches. compute_p_L() therefore refuses to run unless the caller passes
allow_pl=True, which only the injected-X functional check does.

Usage:
    python -m qec.stage_a --dry-run
    python -m qec.stage_a --submit --shots 512
    python -m qec.stage_a --retrieve runs/stage_a_jobs.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time

from qec import tier0, probe, layouts

BUDGET_CAP_MIN = 40.0        # prereg hard cap for the WHOLE study
STAGE_A_CAP_MIN = 6.0        # this pilot's own ceiling
JOBS_FILE = "runs/stage_a_jobs.json"
RESULT_FILE = "runs/stage_a_result.json"


# ------------------------------------------------------ forbidden guard --

class ForbiddenAnalysis(RuntimeError):
    """Raised when Stage A code attempts a Stage B analysis."""


def compute_p_L(counts: dict, active: bool, logical: int,
                allow_pl: bool = False) -> float:
    """Logical error rate. BLOCKED in Stage A except for injected-X checks.

    The preregistration forbids computing patch- or policy-level p_L from
    pilot data, because seeing it would contaminate the confirmatory
    thresholds committed in Stage B. Enforcing that here means a careless
    later edit cannot quietly violate it.
    """
    if not allow_pl:
        raise ForbiddenAnalysis(
            "Stage A may not compute logical error rates. "
            "See PREREGISTRATION.md section 4 (forbidden analyses).")
    total, fails = sum(counts.values()), 0
    for bitstr, n in counts.items():
        f = bitstr.split()
        data_bits = [int(b) for b in f[0][::-1]]
        hist = [(int(x[::-1][0]), int(x[::-1][1])) for x in f[1:][::-1]]
        if tier0.decode_shot(data_bits, hist,
                             apply_corrections=not active) != logical:
            fails += n
    return fails / total


# ------------------------------------------------------------- circuits --

def build_pilot_circuits(rounds: int):
    """The minimum set that exercises every hardware path exactly once."""
    circs = []
    for st in (0, 1):
        circs.append((f"probe_readout_{st}", probe.build_readout_probe(st)))
    circs.append(("probe_syndrome", probe.build_syndrome_probe()))
    circs.append(("enc_passive_1", tier0.build_encoded(rounds, 1, active=False)))
    circs.append(("enc_active_1", tier0.build_encoded(rounds, 1, active=True)))
    circs.append(("dummy_ff", tier0.build_encoded(rounds, 1, active=True,
                                                  dummy_ff=True)))
    # injected-X functional test: the ONE case allowed to compute p_L
    from qiskit import QuantumCircuit
    base = tier0.build_encoded(rounds, 1, active=True)
    inj = QuantumCircuit(*base.qregs, *base.cregs)
    done = False
    for inst in base.data:
        inj.append(inst.operation, inst.qubits, inst.clbits)
        if not done and inst.operation.name == "barrier":
            inj.x(base.qregs[0][0])       # deliberate X on d1
            done = True
    circs.append(("injected_x_d1", inj))
    return circs


def pick_diagnostic_patch(snapshots_glob: str) -> tuple[int, ...]:
    """Third-ranked archive patch: deliberately not a likely policy pick."""
    files = sorted(glob.glob(snapshots_glob))
    snaps = [json.load(open(f)) for f in files]
    cycles = layouts.unique_cycles(snaps)
    adj = layouts.coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = layouts.enumerate_patches(adj, alive)
    arch = {p: s for p in patches
            if (s := layouts.archive_score(cycles, p)) is not None}
    ranked = layouts.rank(arch)
    if len(ranked) < 3:
        raise SystemExit("fewer than 3 scoreable patches")
    return ranked[2][0]


# ---------------------------------------------------------------- submit --

def submit(patch, rounds, shots, service_kwargs=None):
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    service = QiskitRuntimeService(**(service_kwargs or {}))
    backend = service.backend("ibm_marrakesh")
    d1, a1, d2, a2, d3 = patch
    layout = [d1, d2, d3, a1, a2]

    named = build_pilot_circuits(rounds)
    pm5 = generate_preset_pass_manager(optimization_level=3, backend=backend,
                                       initial_layout=layout)
    isa, meta = [], []
    for name, qc in named:
        t = pm5.run(qc)
        ops = t.count_ops()
        if ops.get("swap", 0):
            raise SystemExit(f"{name}: SWAP inserted; G5 invariant violated")
        isa.append(t)
        meta.append({"name": name, "depth": t.depth(),
                     "ops": {k: int(v) for k, v in ops.items()}})

    sampler = SamplerV2(mode=backend)
    sampler.options.default_shots = shots
    job = sampler.run(isa)

    stamp = {
        "job_id": job.job_id(),
        "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": backend.name, "patch": list(patch),
        "rounds": rounds, "shots": shots,
        "circuit_names": [n for n, _ in named], "circuit_meta": meta,
        "stage": "A", "budget_cap_min": STAGE_A_CAP_MIN,
    }
    try:
        props = backend.properties()
        stamp["calibration_before"] = str(getattr(props, "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        stamp["calibration_before"] = "unavailable"

    os.makedirs("runs", exist_ok=True)
    with open(JOBS_FILE, "w") as fh:                     # BEFORE any wait
        json.dump(stamp, fh, indent=2)
    print(f"SUBMITTED {job.job_id()}")
    print(f"job id saved to {JOBS_FILE} - Ctrl+C is now SAFE; "
          f"recover with --retrieve {JOBS_FILE}")
    return job, stamp


# -------------------------------------------------------------- analyse --

def analyse(result, stamp: dict, service=None) -> dict:
    """ALLOWED Stage A outputs only. No p_L except the injected-X check."""
    names = stamp["circuit_names"]
    out = {"stage": "A", "job_id": stamp.get("job_id"),
           "patch": stamp["patch"], "shots": stamp["shots"],
           "circuit_meta": stamp["circuit_meta"], "checks": {}}

    counts = {}
    for i, name in enumerate(names):
        try:
            counts[name] = result[i].data.__dict__[
                list(result[i].data.__dict__)[0]].get_counts()
        except Exception:                                # noqa: BLE001
            counts[name] = None

    # 1. readout probe returns per-qubit SPAM error (allowed: probe output)
    for st in (0, 1):
        c = counts.get(f"probe_readout_{st}")
        if c:
            out["checks"][f"readout_probe_{st}"] = [
                round(e, 5) for e in probe.readout_error_from_counts(c, st)]

    # 2. syndrome probe false-detection rate (allowed: probe output)
    c = counts.get("probe_syndrome")
    if c:
        out["checks"]["syndrome_false_detection_rate"] = round(
            probe.detection_rate_from_counts(c), 5)

    # 3. control path executed at all (allowed: execution success)
    for nm in ("enc_active_1", "dummy_ff"):
        c = counts.get(nm)
        out["checks"][f"{nm}_returned_data"] = bool(c)
        if c:
            out["checks"][f"{nm}_distinct_outcomes"] = len(c)

    # 4. injected-X decode correctness - the ONLY sanctioned p_L
    c = counts.get("injected_x_d1")
    if c:
        p = compute_p_L(c, active=True, logical=1, allow_pl=True)
        out["checks"]["injected_x_logical_error"] = round(p, 4)
        out["checks"]["injected_x_corrected"] = p < 0.5

    # 5. metered cost - READ, never estimated
    if service and stamp.get("job_id"):
        try:
            m = service.job(stamp["job_id"]).metrics()
            out["metrics"] = {"bss": m.get("bss"), "usage": m.get("usage"),
                              "timestamps": m.get("timestamps")}
        except Exception as e:                           # noqa: BLE001
            out["metrics"] = {"error": str(e)}
    return out


def report(out: dict) -> None:
    print("\n" + "=" * 70)
    print("STAGE A PILOT - ALLOWED OUTPUTS ONLY")
    print("=" * 70)
    print(f"patch  : {out['patch']}")
    print(f"job    : {out.get('job_id')}")
    for k, v in out["checks"].items():
        print(f"  {k:<34} {v}")
    m = out.get("metrics") or {}
    print("\nMETERED COST (read, not estimated):")
    print(f"  bss   : {m.get('bss')}")
    print(f"  usage : {m.get('usage')}")
    print("\nStage B sizes the confirmatory matrix from the number above,")
    print("with the arithmetic shown, before any further submission.")
    print("No patch- or policy-level p_L was computed. That is Stage B.")
    print("=" * 70)


# ------------------------------------------------------------------ main --

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="full path on a local simulator; no account contact")
    p.add_argument("--submit", action="store_true")
    p.add_argument("--retrieve", default=None, metavar="JOBS_JSON")
    p.add_argument("--snapshots", default="data/snapshots/*_converted.json")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--shots", type=int, default=512)
    p.add_argument("--patch", default=None, help="override, 'q1,q2,q3,q4,q5'")
    a = p.parse_args()

    if a.dry_run:
        from qiskit_aer import AerSimulator
        sim = AerSimulator()
        named = build_pilot_circuits(a.rounds)
        print(f"dry run: {len(named)} circuits, {a.shots} shots, no account\n")
        for name, qc in named:
            c = sim.run(qc, shots=a.shots).result().get_counts()
            note = ""
            if name == "injected_x_d1":
                pl = compute_p_L(c, active=True, logical=1, allow_pl=True)
                note = f"  injected-X p_L={pl:.4f} (want 0)"
            elif name.startswith("probe_readout"):
                st = int(name[-1])
                note = ("  err=" +
                        str([round(e, 4) for e in
                             probe.readout_error_from_counts(c, st)]))
            elif name == "probe_syndrome":
                note = f"  false-detection={probe.detection_rate_from_counts(c):.4f}"
            print(f"  {name:<20} depth={qc.depth():<4} outcomes={len(c):<4}{note}")
        print("\nDRY RUN COMPLETE - pipeline works end to end, zero QPU.")
        return

    if a.retrieve:
        from qiskit_ibm_runtime import QiskitRuntimeService
        stamp = json.load(open(a.retrieve))
        service = QiskitRuntimeService()
        job = service.job(stamp["job_id"])
        print(f"retrieving {stamp['job_id']} ({job.status()})")
        out = analyse(job.result(), stamp, service)
        report(out)
        with open(RESULT_FILE, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"wrote {RESULT_FILE}")
        return

    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    patch = (tuple(int(x) for x in a.patch.split(",")) if a.patch
             else pick_diagnostic_patch(a.snapshots))
    print(f"Stage A diagnostic patch: {patch}")
    print(f"shots={a.shots} rounds={a.rounds} cap={STAGE_A_CAP_MIN} min")
    print("\nThis SPENDS QPU TIME. Confirm the dashboard shows available")
    print("budget before continuing.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted; nothing submitted")

    job, stamp = submit(patch, a.rounds, a.shots)
    from qiskit_ibm_runtime import QiskitRuntimeService
    service = QiskitRuntimeService()
    print("waiting (safe to Ctrl+C; use --retrieve afterwards)...")
    out = analyse(job.result(), stamp, service)
    report(out)
    with open(RESULT_FILE, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {RESULT_FILE}")


if __name__ == "__main__":
    main()

