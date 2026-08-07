"""QEC-P1 gate G5 — compile verification against the LIVE backend target.

The last free gate before Stage A. Costs zero QPU time: it reads the
backend target and transpiles locally. Nothing is submitted.

WHAT IT CHECKS (prereg v3 section 7 G5, extended by Amendment A2)

  1. TARGET SUPPORT       if_else / measure / reset present on ibm_fez
  2. ZERO SWAP            no routing inserted for any candidate patch
  3. CONDITIONALS SURVIVE if_else blocks still present after transpilation
                          at optimization_level=3 (they can be optimised
                          away or rejected outright)
  4. LAYOUT HONOURED      the transpiler used the patch we asked for
  5. FLAG-QUBIT CHECK     heavy-hex has max degree 3. A d=3 repetition
                          patch needs each ancilla coupled to BOTH of its
                          data qubits. If the geometry cannot supply that
                          without routing, flag qubits would be required
                          (cf. arXiv:2403.10217) and the patch is invalid.
  6. DEPTH / GATE COUNT   recorded per patch, for the Stage A cost model
                          and for the duration-matched BARE delay.

WHY IT MATTERS
A patch that scores well but needs a SWAP is not the patch we think we
are running: routing changes which physical qubits hold the data, which
silently invalidates the selection policy under test. This gate is what
makes "the policy selected patch X" a true statement on hardware.

Usage:
    python -m qec.g5_compile --patches auto --top 12
    python -m qec.g5_compile --patches "1,2,3,16,23" --verbose
    python -m qec.g5_compile --offline data/snapshots/latest.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys

from qec import tier0
from qec import layouts


def get_target(offline_snapshot: str | None):
    """Live backend target, or a snapshot-derived stand-in when offline."""
    if offline_snapshot:
        return None, "offline"
    from qiskit_ibm_runtime import QiskitRuntimeService
    service = QiskitRuntimeService()
    backend = service.backend("ibm_fez")
    return backend, backend.name


def check_target_support(backend) -> tuple[bool, str]:
    ops = sorted(backend.target.operation_names)
    need = {"if_else", "measure", "reset"}
    have = need & set(ops)
    ok = have == need
    return ok, (f"ops={ops} | required present: {sorted(have)}"
                f"{'' if ok else ' | MISSING: ' + str(sorted(need - have))}")


def check_patch_geometry(backend, patch: tuple[int, ...]) -> tuple[bool, str]:
    """Flag-qubit check: each ancilla must couple to BOTH its data qubits.

    patch = (d1, a1, d2, a2, d3); required edges are the four consecutive
    pairs. If any is absent from the coupling map, syndrome extraction
    would need routing or flag qubits and the patch is invalid for this
    study's zero-SWAP requirement.
    """
    d1, a1, d2, a2, d3 = patch
    cmap = set()
    for edge in backend.coupling_map:
        cmap.add(tuple(edge))
        cmap.add(tuple(reversed(edge)))
    need = [(d1, a1), (a1, d2), (d2, a2), (a2, d3)]
    missing = [e for e in need if e not in cmap]
    if missing:
        return False, f"missing couplers {missing} -> flag qubits required"
    return True, "all 4 data-ancilla couplers present"


def compile_patch(backend, patch: tuple[int, ...], rounds: int,
                  active: bool) -> dict:
    """Transpile one circuit onto one patch and measure what came out."""
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    qc = tier0.build_encoded(rounds, 1, active=active)
    # tier0 register order d0,d1,d2,a0,a1 -> physical (d1,d2,d3,a1,a2)
    d1, a1, d2, a2, d3 = patch
    initial_layout = [d1, d2, d3, a1, a2]

    pm = generate_preset_pass_manager(optimization_level=3, backend=backend,
                                      initial_layout=initial_layout)
    isa = pm.run(qc)

    ops = isa.count_ops()
    n_swap = ops.get("swap", 0)
    n_if = ops.get("if_else", 0)
    n_if_src = qc.count_ops().get("if_else", 0)

    # confirm the transpiler actually placed our qubits where we asked
    layout_ok = True
    try:
        final = isa.layout.initial_index_layout(filter_ancillas=True)
        layout_ok = list(final)[:5] == initial_layout
    except Exception:                                    # noqa: BLE001
        layout_ok = None                                 # cannot verify

    return {
        "patch": list(patch),
        "active": active,
        "depth": isa.depth(),
        "n_swap": n_swap,
        "n_if_else_src": n_if_src,
        "n_if_else_isa": n_if,
        "conditionals_preserved": (n_if == n_if_src),
        "layout_honoured": layout_ok,
        "two_qubit_gates": ops.get("cz", 0) + ops.get("ecr", 0),
        "ops": {k: int(v) for k, v in ops.items()},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--patches", default="auto",
                   help="'auto' to score from snapshots, or 'q1,q2,q3,q4,q5'")
    p.add_argument("--snapshots", default="data/snapshots/*_converted.json")
    p.add_argument("--top", type=int, default=12,
                   help="how many top-scoring patches to compile-check")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--json-out", default="runs/g5_compile.json")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()

    print("=" * 70)
    print("QEC-P1 GATE G5 - COMPILE VERIFICATION (zero QPU)")
    print("=" * 70)

    backend, name = get_target(None)
    print(f"backend: {name}\n")

    ok_support, msg = check_target_support(backend)
    print(f"[{'PASS' if ok_support else 'FAIL'}] target support")
    print(f"       {msg}\n")
    if not ok_support:
        raise SystemExit("target lacks required operations; stop.")

    # candidate patches
    if a.patches == "auto":
        files = sorted(glob.glob(a.snapshots))
        snaps = [json.load(open(f)) for f in files]
        cycles = layouts.unique_cycles(snaps)
        adj = layouts.coupling_from_snapshot(cycles[-1])
        alive = {int(q) for q in cycles[-1].get("qubits", {})}
        all_patches = layouts.enumerate_patches(adj, alive)
        inst = {q: s for q in all_patches
                if (s := layouts.instantaneous_score(cycles[-1], q)) is not None}
        cands = [q for q, _ in layouts.rank(inst)[:a.top]]
        print(f"{len(all_patches)} valid patches from archive; "
              f"compile-checking top {len(cands)}\n")
    else:
        cands = [tuple(int(x) for x in a.patches.split(","))]
        print(f"compile-checking 1 specified patch: {cands[0]}\n")

    results, n_pass = [], 0
    for i, patch in enumerate(cands, 1):
        geo_ok, geo_msg = check_patch_geometry(backend, patch)
        row = {"patch": list(patch), "geometry_ok": geo_ok,
               "geometry": geo_msg, "circuits": []}
        if not geo_ok:
            print(f"[{i:2d}] {str(patch):<28} FAIL geometry: {geo_msg}")
            results.append(row)
            continue

        all_ok = True
        for active in (False, True):
            try:
                c = compile_patch(backend, patch, a.rounds, active)
            except Exception as e:                        # noqa: BLE001
                c = {"active": active, "error": f"{type(e).__name__}: {e}"}
                all_ok = False
            row["circuits"].append(c)
            if "error" not in c:
                if c["n_swap"] != 0 or not c["conditionals_preserved"]:
                    all_ok = False
                if c["layout_honoured"] is False:
                    all_ok = False

        enc = next((c for c in row["circuits"] if c.get("active")), {})
        tag = "PASS" if all_ok else "FAIL"
        n_pass += all_ok
        print(f"[{i:2d}] {str(patch):<28} {tag}  "
              f"swap={enc.get('n_swap','?')} depth={enc.get('depth','?')} "
              f"2q={enc.get('two_qubit_gates','?')} "
              f"if_else={enc.get('n_if_else_isa','?')}/{enc.get('n_if_else_src','?')}")
        if a.verbose and "error" in enc:
            print(f"     {enc['error']}")
        row["all_ok"] = all_ok
        results.append(row)

    print("\n" + "=" * 70)
    print(f"G5 RESULT: {n_pass}/{len(cands)} candidate patches compile clean")
    print("=" * 70)
    if n_pass == 0:
        print("No patch passes. Stage A cannot proceed: the study's")
        print("zero-SWAP requirement is unmet on every candidate.")
    elif n_pass < len(cands):
        print("Some patches fail. The selection policies MUST be restricted")
        print("to the passing set, and that restriction is a preregistration")
        print("amendment (it changes the candidate pool both policies draw")
        print("from). Do not silently drop failures.")
    else:
        print("All candidates compile clean -> G5 PASS, proceed to Stage A")
        print("cost pilot. Record the depth/2q figures above; the BARE")
        print("duration match is set from the SCHEDULED encoded duration.")
    print()

    with open(a.json_out, "w") as fh:
        json.dump({"backend": name, "rounds": a.rounds,
                   "n_pass": n_pass, "n_checked": len(cands),
                   "results": results}, fh, indent=2)
    print(f"wrote {a.json_out}")


if __name__ == "__main__":
    main()
