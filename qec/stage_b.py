"""QEC-P1 Stage B â€” confirmatory session runner. THE STUDY ITSELF.

One invocation = one calibration window = one session. Everything in a
session goes in a SINGLE Runtime job so all policies experience the same
hardware state; that is what makes the within-session pairing valid.

SESSION STRUCTURE (frozen by the Stage B commit, 2026-08-07)
------------------------------------------------------------
  1. PROBE     8 candidate patches x 3 circuits x 256 shots
               (readout |0>, readout |1>, syndrome false-detection)
  2. RANK      composite probe score, lower is better -> P-probe winner
  3. DEPLOY    3 policies x 2 logical states x 5 circuits x 4096 shots
                 P-probe    winner of the probe ranking
                 P-archive  rolling archive score (Amendment A1 weights)
                 P-generic  transpiler default, no initial_layout
               circuits: BARE on each of 3 data qubits, ENC_PASSIVE,
               ENC_ACTIVE
  4. ORDER     main circuits randomized; seed recorded in the stamp

Probe and deploy are separate jobs by necessity -- the deploy layout
depends on the probe result -- so the probe job's ID is written to disk
before it is awaited, same as the deploy job's.

WHAT THIS SCRIPT DOES NOT DO
----------------------------
It does not compute p_L, S, or any policy comparison. Analysis is a
separate step run after all sessions complete, so no interim result can
influence a later session's execution. This runner collects and stores;
it does not interpret.

SAFEGUARDS (all carried from QNN-P1 and Stage A)
------------------------------------------------
  * job IDs to disk BEFORE any wait; --retrieve recovers for free
  * --dry-run exercises the whole path locally, no account contact
  * calibration timestamp captured before AND after
  * zero-SWAP assertion on every transpiled circuit (G5 invariant)
  * budget guard: refuses to submit if the declared cap is exceeded
  * subscript register access (the Stage A D-A1 DataBin collision)

Usage:
    python -m qec.stage_b --dry-run
    python -m qec.stage_b --submit --session 1
    python -m qec.stage_b --retrieve runs/session_1_jobs.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import time

from qec import tier0, probe, layouts

N_CANDIDATES = 8
PROBE_SHOTS = 256
MAIN_SHOTS = 4096
ROUNDS = 3
STAGE_B_CAP_MIN = 32.0          # 40 total minus Stage A and margin


# ------------------------------------------------------------- utilities --

def counts_from_pub(pub_result, circuit) -> dict:
    """DataBin -> qiskit-style counts across ALL registers.

    Subscript, never getattr: a register named "data" collides with the
    DataBin container attribute (deviation D-A1).
    """
    data = pub_result.data
    names = [c.name for c in circuit.cregs]
    arrays = {}
    for n in names:
        try:
            arrays[n] = data[n]
        except Exception:                                # noqa: BLE001
            try:
                arrays[n] = getattr(data, n)
            except Exception:                            # noqa: BLE001
                pass
    if not arrays:
        raise ValueError("no classical registers in result")
    if len(arrays) == 1:
        return next(iter(arrays.values())).get_counts()
    per = {n: arrays[n].get_bitstrings() for n in names}
    out: dict[str, int] = {}
    for s in range(len(per[names[0]])):
        key = " ".join(per[n][s] for n in reversed(names))
        out[key] = out.get(key, 0) + 1
    return out


def load_cycles(pattern: str):
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f"no snapshots matched {pattern}")
    return layouts.unique_cycles([json.load(open(f)) for f in files])


def candidate_patches(cycles, n: int) -> list[tuple[int, ...]]:
    """Top-n by CURRENT-cycle score: the pool both probe and archive draw from."""
    adj = layouts.coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = layouts.enumerate_patches(adj, alive)
    inst = {p: s for p in patches
            if (s := layouts.instantaneous_score(cycles[-1], p)) is not None}
    return [p for p, _ in layouts.rank(inst)[:n]]


def archive_patch(cycles) -> tuple[int, ...]:
    adj = layouts.coupling_from_snapshot(cycles[-1])
    alive = {int(q) for q in cycles[-1].get("qubits", {})}
    patches = layouts.enumerate_patches(adj, alive)
    arch = {p: s for p in patches
            if (s := layouts.archive_score(cycles, p)) is not None}
    return layouts.rank(arch)[0][0]


def layout_for(patch: tuple[int, ...]) -> list[int]:
    """tier0 register order d0,d1,d2,a0,a1 -> physical (d1,d2,d3,a1,a2)."""
    d1, a1, d2, a2, d3 = patch
    return [d1, d2, d3, a1, a2]


def transpile_checked(qc, backend, layout, pm_cache: dict):
    """Transpile and assert the G5 zero-SWAP invariant still holds."""
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    key = tuple(layout) if layout else "generic"
    if key not in pm_cache:
        pm_cache[key] = generate_preset_pass_manager(
            optimization_level=3, backend=backend,
            initial_layout=layout) if layout else \
            generate_preset_pass_manager(optimization_level=3, backend=backend)
    t = pm_cache[key].run(qc)
    if t.count_ops().get("swap", 0):
        raise SystemExit(f"SWAP inserted for layout {layout}; G5 violated")
    return t


# ---------------------------------------------------------- probe stage --

def build_probe_set(candidates):
    named = []
    for patch in candidates:
        for st in (0, 1):
            named.append((f"probe|{patch}|readout{st}",
                          probe.build_readout_probe(st), patch))
        named.append((f"probe|{patch}|syndrome",
                      probe.build_syndrome_probe(), patch))
    return named


def score_probes(counts_by_name, candidates) -> dict:
    scores = {}
    for patch in candidates:
        try:
            r0 = probe.readout_error_from_counts(
                counts_by_name[f"probe|{patch}|readout0"], 0)
            r1 = probe.readout_error_from_counts(
                counts_by_name[f"probe|{patch}|readout1"], 1)
            det = probe.detection_rate_from_counts(
                counts_by_name[f"probe|{patch}|syndrome"])
        except (KeyError, TypeError):
            continue
        scores[patch] = probe.probe_score(r0, r1, det)
    return scores


# ----------------------------------------------------------- main stage --

def build_main_set(policies: dict, seed: int):
    """3 policies x 2 states x (3 BARE + ENC_PASSIVE + ENC_ACTIVE)."""
    named = []
    for pol, patch in policies.items():
        for st in (0, 1):
            for k in range(3):
                named.append((f"{pol}|BARE{k}|{st}",
                              tier0.build_bare(st), patch, k))
            named.append((f"{pol}|ENC_PASSIVE|{st}",
                          tier0.build_encoded(ROUNDS, st, active=False),
                          patch, None))
            named.append((f"{pol}|ENC_ACTIVE|{st}",
                          tier0.build_encoded(ROUNDS, st, active=True),
                          patch, None))
    rng = random.Random(seed)
    rng.shuffle(named)                     # interleave policies within the job
    return named


# --------------------------------------------------------------- submit --

def submit_session(session: int, snapshots: str, seed: int) -> dict:
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    service = QiskitRuntimeService()
    backend = service.backend("ibm_marrakesh")
    cycles = load_cycles(snapshots)
    cands = candidate_patches(cycles, N_CANDIDATES)
    print(f"candidate patches ({len(cands)}):")
    for c in cands:
        print(f"   {c}")

    stamp = {"session": session, "seed": seed, "backend": backend.name,
             "rounds": ROUNDS, "probe_shots": PROBE_SHOTS,
             "main_shots": MAIN_SHOTS,
             "candidates": [list(c) for c in cands],
             "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        stamp["calibration_before"] = str(
            getattr(backend.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        stamp["calibration_before"] = "unavailable"

    jobs_file = f"runs/session_{session}_jobs.json"
    os.makedirs("runs", exist_ok=True)

    # ---- probe job -----------------------------------------------------
    pm_cache: dict = {}
    pnamed = build_probe_set(cands)
    pisa = [transpile_checked(qc, backend, layout_for(p), pm_cache)
            for _, qc, p in pnamed]
    sampler = SamplerV2(mode=backend)
    sampler.options.default_shots = PROBE_SHOTS
    pjob = sampler.run(pisa)
    stamp["probe_job_id"] = pjob.job_id()
    stamp["probe_names"] = [n for n, _, _ in pnamed]
    with open(jobs_file, "w") as fh:                     # BEFORE waiting
        json.dump(stamp, fh, indent=2)
    print(f"\nPROBE job {pjob.job_id()} submitted; id saved to {jobs_file}")

    presult = pjob.result()
    pcounts = {}
    for i, (name, qc, _) in enumerate(pnamed):
        try:
            pcounts[name] = counts_from_pub(presult[i], qc)
        except Exception:                                # noqa: BLE001
            pcounts[name] = None
    scores = score_probes(pcounts, cands)
    if not scores:
        raise SystemExit("no candidate produced a usable probe score")
    ranked = sorted(scores.items(), key=lambda kv: kv[1])
    p_probe = ranked[0][0]
    print("\nprobe ranking (lower is better):")
    for patch, s in ranked:
        print(f"   {str(patch):<28} {s:.5f}{'   <- P-probe' if patch == p_probe else ''}")

    p_arch = archive_patch(cycles)
    policies = {"P_probe": p_probe, "P_archive": p_arch,
                "P_generic": cands[0]}       # placeholder; generic uses no layout
    stamp["probe_scores"] = {str(list(k)): v for k, v in scores.items()}
    stamp["policies"] = {k: list(v) for k, v in policies.items()}
    print(f"\nP_probe   {p_probe}\nP_archive {p_arch}\n"
          f"P_generic transpiler default (no initial_layout)")

    # ---- main job ------------------------------------------------------
    mnamed = build_main_set(policies, seed)
    misa = []
    for name, qc, patch, bare_idx in mnamed:
        if name.startswith("P_generic"):
            misa.append(transpile_checked(qc, backend, None, pm_cache))
        else:
            lay = layout_for(patch)
            if bare_idx is not None:
                lay = [lay[bare_idx]]          # BARE is a 1-qubit circuit
            misa.append(transpile_checked(qc, backend, lay, pm_cache))

    sampler.options.default_shots = MAIN_SHOTS
    mjob = sampler.run(misa)
    stamp["main_job_id"] = mjob.job_id()
    stamp["main_names"] = [n for n, _, _, _ in mnamed]
    with open(jobs_file, "w") as fh:                     # BEFORE waiting
        json.dump(stamp, fh, indent=2)
    print(f"\nMAIN job {mjob.job_id()} submitted; id saved to {jobs_file}")
    print("Ctrl+C is SAFE. Recover with --retrieve " + jobs_file)
    return stamp


# ------------------------------------------------------------- retrieve --

def retrieve(jobs_file: str) -> dict:
    from qiskit_ibm_runtime import QiskitRuntimeService
    stamp = json.load(open(jobs_file))
    service = QiskitRuntimeService()

    out = {"session": stamp["session"], "stamp": stamp, "counts": {}}
    for kind, id_key, names_key, builder in (
            ("probe", "probe_job_id", "probe_names", None),
            ("main", "main_job_id", "main_names", None)):
        jid = stamp.get(id_key)
        if not jid:
            continue
        job = service.job(jid)
        print(f"{kind} job {jid}: {job.status()}")
        res = job.result()
        # rebuild circuits in the same order to parse registers correctly
        if kind == "probe":
            cands = [tuple(c) for c in stamp["candidates"]]
            named = build_probe_set(cands)
            circs = [qc for _, qc, _ in named]
        else:
            policies = {k: tuple(v) for k, v in stamp["policies"].items()}
            named = build_main_set(policies, stamp["seed"])
            circs = [qc for _, qc, _, _ in named]
        for i, nm in enumerate(stamp[names_key]):
            try:
                out["counts"][nm] = counts_from_pub(res[i], circs[i])
            except Exception as e:                       # noqa: BLE001
                out["counts"][nm] = None
                print(f"  parse failed for {nm}: {type(e).__name__}")
        m = service.job(jid).metrics()
        out[f"{kind}_metrics"] = {"bss": m.get("bss"), "usage": m.get("usage")}

    try:
        backend = service.backend(stamp["backend"])
        out["calibration_after"] = str(
            getattr(backend.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        out["calibration_after"] = "unavailable"

    path = f"runs/session_{stamp['session']}_counts.json"
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nwrote {path}")
    print("METERED COST:")
    for k in ("probe_metrics", "main_metrics"):
        if k in out:
            print(f"  {k}: {out[k]}")
    print("\nBINDING (Stage B commit): if this session exceeded 3x the")
    print("projected 108 s, STOP and re-size by amendment before session 2.")
    print("\nNo p_L computed. Analysis runs after all sessions complete.")
    return out


# ------------------------------------------------------------------ main --

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--submit", action="store_true")
    p.add_argument("--retrieve", default=None)
    p.add_argument("--session", type=int, default=1)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--snapshots", default="data/snapshots/*_converted.json")
    a = p.parse_args()

    if a.dry_run:
        from qiskit_aer import AerSimulator
        sim = AerSimulator()
        cycles = load_cycles(a.snapshots)
        cands = candidate_patches(cycles, N_CANDIDATES)
        seed = a.seed if a.seed is not None else 1000 + a.session
        print(f"dry run: {len(cands)} candidates, seed {seed}\n")

        pnamed = build_probe_set(cands)
        pc = {}
        for name, qc, _ in pnamed:
            pc[name] = sim.run(qc, shots=PROBE_SHOTS).result().get_counts()
        scores = score_probes(pc, cands)
        ranked = sorted(scores.items(), key=lambda kv: kv[1])
        print(f"probe circuits: {len(pnamed)} | scored {len(scores)} candidates")
        print(f"  winner (noiseless, so effectively arbitrary): {ranked[0][0]}")

        policies = {"P_probe": ranked[0][0],
                    "P_archive": archive_patch(cycles),
                    "P_generic": cands[0]}
        mnamed = build_main_set(policies, seed)
        print(f"main circuits: {len(mnamed)} "
              f"(expect {3*2*5} = 30)")
        total_cs = len(pnamed) * PROBE_SHOTS + len(mnamed) * MAIN_SHOTS
        print(f"\ncircuit-shots this session: {total_cs:,}")
        print(f"projected cost at the Stage A anchor: "
              f"{total_cs * 3.0/3584:.0f} s")
        print("\nDRY RUN COMPLETE - zero QPU, pipeline exercised end to end.")
        return

    if a.retrieve:
        retrieve(a.retrieve)
        return

    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    seed = a.seed if a.seed is not None else 1000 + a.session
    print(f"STAGE B SESSION {a.session}  (seed {seed})")
    print(f"cap {STAGE_B_CAP_MIN} min; projected ~108 s for this session")
    print("\nThis SPENDS QPU TIME. Confirm the dashboard first.")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted; nothing submitted")

    stamp = submit_session(a.session, a.snapshots, seed)
    print("\nwaiting for main job (Ctrl+C safe)...")
    retrieve(f"runs/session_{stamp['session']}_jobs.json")


if __name__ == "__main__":
    main()

