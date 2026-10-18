"""QEC-P1 multiverse pre-flight -- zero QPU. Run before each new window.

Checks, against the live backend:
  1. backend operational, queue depth
  2. calibration has CHANGED since the previous window (else it's not a new window)
  3. every pinned patch: no qubit or coupler reporting error >= 1.0 (IBM's
     'undefined/failed benchmark' value), and the worst readout / CZ error

Usage (from the repo root, in WSL):
    python -m qec.mv_preflight --pin-from runs/g6ext_1_result.json --previous runs/g6ext_1_result.json
For window 3, pass --previous runs/g6ext_2_result.json
"""
import argparse, json


def load_stamp(path):
    d = json.load(open(path))
    return d.get("stamp", d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pin-from", required=True)
    ap.add_argument("--previous", required=True, help="result/stamp file of the previous window")
    ap.add_argument("--backend", default="ibm_marrakesh")
    a = ap.parse_args()

    from qiskit_ibm_runtime import QiskitRuntimeService
    be = QiskitRuntimeService().backend(a.backend)
    st = be.status()
    print(f"{be.name}: operational={st.operational} status='{st.status_msg}' pending_jobs={st.pending_jobs}")

    props = be.properties()
    now_cal = str(getattr(props, "last_update_date", "n/a"))
    prev_cal = load_stamp(a.previous).get("calibration_before", "n/a")
    print(f"calibration now      : {now_cal}")
    print(f"previous window's cal: {prev_cal}")
    cal_ok = now_cal != prev_cal and now_cal != "n/a"
    print("  -> NEW calibration cycle" if cal_ok else "  -> SAME cycle: do NOT submit yet")

    target = be.target
    gate = "cz" if "cz" in target.operation_names else "ecr"
    bad = []
    print(f"\n{'patch':<24}{'max readout':>12}{'max ' + gate:>12}   flags")
    for patch in load_stamp(a.pin_from)["candidates"]:
        ro = [props.readout_error(q) for q in patch]
        cz = []
        for q1, q2 in zip(patch, patch[1:]):          # path d1-a1-d2-a2-d3
            e = None
            for pair in ((q1, q2), (q2, q1)):
                try:
                    e = target[gate][pair].error
                    break
                except KeyError:
                    continue
            cz.append(e)
        flags = []
        if any(x is not None and x >= 1.0 for x in ro + cz):
            flags.append("ERROR>=1.0")
        if any(x is None for x in cz):
            flags.append("MISSING COUPLER")
        if flags:
            bad.append((patch, flags))
        cz_known = [x for x in cz if x is not None]
        print(f"{str(tuple(patch)):<24}{max(ro):>12.4f}{(max(cz_known) if cz_known else float('nan')):>12.4f}   {' '.join(flags) or 'ok'}")

    print()
    if not st.operational:
        print("STOP: backend not operational")
    elif not cal_ok:
        print("STOP: calibration has not changed since the previous window")
    elif bad:
        print("STOP: a pinned patch is broken on today's calibration. Do not drop or swap it")
        print("on your own; record it and decide the handling before submitting.")
    else:
        print("GO: all checks passed")


if __name__ == "__main__":
    main()
