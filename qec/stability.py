"""QEC-P1 Q-E — is the target itself stable? (Amendment A7)

Five selection instruments have failed to predict d=3 repetition-code
logical error on this device. This asks whether the quantity being
predicted is stable enough to BE predicted.

DESIGN
------
Two patches (the two that moved most between the Aug 16 and Aug 17
windows), ENC_ACTIVE |1_L>, 4096 shots, identical circuits:

  Job A  6 repeats of each, INTERLEAVED p1,p2,p1,p2,...  (seconds scale)
  Job B  the identical job resubmitted immediately        (minutes scale)

Interleaving is load-bearing: run in blocks, any within-job drift would
be indistinguishable from a patch difference.

FROZEN ANALYSIS (A7 section 4)
------------------------------
chi-square test of homogeneity across the 6 repeats, per patch per job.
Under the null all 6 are binomial samples from one p. Expected counts
exceed 1000, so the approximation holds.

Also: observed spread vs binomial sd; Spearman rho of p_L against repeat
index (monotone drift); A-vs-B difference per patch.

INTERPRETATION IS PRE-DECLARED IN BOTH DIRECTIONS (A7 section 5),
INCLUDING THE OUTCOME THAT ARGUES AGAINST THE HYPOTHESIS.

Usage:
    python -m qec.stability --dry-run
    python -m qec.stability --submit
    python -m qec.stability --retrieve runs/stability_jobs.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time

from qec import tier0, stage_b

PATCHES = [(53, 54, 55, 59, 75), (1, 2, 3, 4, 5)]
REPEATS = 6
SHOTS = 4096
ROUNDS = 3
STATE = 1
JOBS_FILE = "runs/stability_jobs.json"


def build_named():
    """Interleaved: p1,p2,p1,p2,... so both patches span the job."""
    named = []
    for r in range(REPEATS):
        for pi, patch in enumerate(PATCHES):
            named.append((f"p{pi}|rep{r}",
                          tier0.build_encoded(ROUNDS, STATE, active=True),
                          stage_b.layout_for(patch)))
    return named


def chi2_homogeneity(ks, ns):
    """Are these binomial samples from one p? Returns (chi2, df, p_approx)."""
    K = sum(ks)
    N = sum(ns)
    p = K / N
    chi2 = 0.0
    for k, n in zip(ks, ns):
        for obs, exp in ((k, n * p), (n - k, n * (1 - p))):
            if exp > 0:
                chi2 += (obs - exp) ** 2 / exp
    df = len(ks) - 1
    # survival function of chi-square via the regularised upper gamma,
    # computed by series so no scipy dependency is introduced
    def sf(x, k):
        if x <= 0:
            return 1.0
        if k % 2 == 0:
            m = k // 2
            t = math.exp(-x / 2)
            s = t
            for i in range(1, m):
                t *= (x / 2) / i
                s += t
            return min(1.0, s)
        # odd df: use the erfc-based form
        s = math.erfc(math.sqrt(x / 2))
        t = math.sqrt(2 * x / math.pi) * math.exp(-x / 2)
        for i in range(1, (k - 1) // 2 + 1):
            s += t
            t *= x / (2 * i + 1)
        return min(1.0, max(0.0, s))
    return chi2, df, sf(chi2, df)


def submit():
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    svc = QiskitRuntimeService()
    be = svc.backend("ibm_marrakesh")
    named = build_named()
    cache = {}
    isa = [stage_b.transpile_checked(qc, be, lay, cache)
           for _, qc, lay in named]

    sampler = SamplerV2(mode=be)
    sampler.options.default_shots = SHOTS

    print("submitting job A (seconds scale)...")
    job_a = sampler.run(isa)
    stamp = {"patches": [list(p) for p in PATCHES], "repeats": REPEATS,
             "shots": SHOTS, "rounds": ROUNDS, "state": STATE,
             "names": [n for n, _, _ in named],
             "job_a": job_a.job_id(),
             "submitted_a": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    os.makedirs("runs", exist_ok=True)
    json.dump(stamp, open(JOBS_FILE, "w"), indent=2)
    print(f"  job A {job_a.job_id()} -> {JOBS_FILE}")

    job_a.result()          # B must follow A, not run concurrently
    print("job A done; submitting job B (minutes scale)...")
    job_b = sampler.run(isa)
    stamp["job_b"] = job_b.job_id()
    stamp["submitted_b"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        stamp["calibration"] = str(
            getattr(be.properties(), "last_update_date", "n/a"))
    except Exception:                                    # noqa: BLE001
        pass
    json.dump(stamp, open(JOBS_FILE, "w"), indent=2)
    print(f"  job B {job_b.job_id()} -> {JOBS_FILE}")
    return JOBS_FILE


def retrieve(jobs_file):
    from qiskit_ibm_runtime import QiskitRuntimeService
    from qec.analyze import enc_pL
    stamp = json.load(open(jobs_file))
    svc = QiskitRuntimeService()
    named = build_named()

    out = {"stamp": stamp, "jobs": {}}
    for tag in ("job_a", "job_b"):
        jid = stamp.get(tag)
        if not jid:
            continue
        job = svc.job(jid)
        print(f"{tag} {jid}: {job.status()}")
        res = job.result()
        cells = {}
        for i, (nm, qc, _) in enumerate(named):
            try:
                c = stage_b.counts_from_pub(res[i], qc)
                k, n = enc_pL(c, stamp["state"], False)
                cells[nm] = {"k": k, "n": n, "p_L": k / n}
            except Exception as e:                       # noqa: BLE001
                print(f"  parse failed {nm}: {type(e).__name__}")
        out["jobs"][tag] = cells
        try:
            out.setdefault("metrics", {})[tag] = job.metrics().get("usage")
        except Exception:                                # noqa: BLE001
            pass

    json.dump(out, open("runs/stability_result.json", "w"), indent=2)
    print("wrote runs/stability_result.json")
    report(out)
    return out


def report(out):
    from qec.analyze import spearman
    stamp = out["stamp"]
    patches = [tuple(p) for p in stamp["patches"]]
    print("\n" + "=" * 74)
    print("Q-E — TEMPORAL STABILITY OF PATCH LOGICAL ERROR")
    print(f"ENC_ACTIVE |{stamp['state']}_L>, {stamp['shots']} shots, "
          f"{stamp['repeats']} interleaved repeats")
    print("=" * 74)

    means = {}
    for tag, label in (("job_a", "JOB A (seconds scale)"),
                       ("job_b", "JOB B (minutes later)")):
        cells = out["jobs"].get(tag)
        if not cells:
            continue
        print(f"\n{label}")
        for pi, patch in enumerate(patches):
            reps = [cells.get(f"p{pi}|rep{r}") for r in range(stamp["repeats"])]
            reps = [x for x in reps if x]
            if len(reps) < 3:
                continue
            ks = [x["k"] for x in reps]
            ns = [x["n"] for x in reps]
            ps = [x["p_L"] for x in reps]
            chi2, df, pv = chi2_homogeneity(ks, ns)
            pbar = sum(ks) / sum(ns)
            binom_sd = math.sqrt(pbar * (1 - pbar) / ns[0])
            obs_sd = statistics.pstdev(ps)
            drift = spearman(list(range(len(ps))), ps)
            means[(tag, patch)] = pbar
            print(f"  {str(patch):<24} p_L per repeat: "
                  f"{[round(x,4) for x in ps]}")
            print(f"  {'':<24} mean={pbar:.4f}  observed sd={obs_sd:.4f}  "
                  f"binomial sd={binom_sd:.4f}  ratio={obs_sd/binom_sd:.2f}x")
            print(f"  {'':<24} chi2={chi2:.1f} df={df} p={pv:.4f}  "
                  f"{'EXCEEDS binomial' if pv < 0.05 else 'consistent with binomial'}")
            if drift is not None:
                print(f"  {'':<24} drift vs repeat index: rho={drift:+.2f}")

    print("\n" + "-" * 74)
    print("A vs B (minutes-scale change)")
    for patch in patches:
        a = means.get(("job_a", patch))
        b = means.get(("job_b", patch))
        if a is None or b is None:
            continue
        print(f"  {str(patch):<24} A={a:.4f}  B={b:.4f}  "
              f"delta={b-a:+.4f}  ({(b-a)/a*100:+.1f}%)")

    print("\n" + "=" * 74)
    print("READING THIS (A7 section 5, declared before the run)")
    print("=" * 74)
    print("within-job EXCEEDS binomial -> target moves on seconds scale;")
    print("   no prior measurement could track it; the five selection")
    print("   failures are fully explained.")
    print("within-job consistent but A != B -> instability is minutes-to-")
    print("   hours; probe and deploy are separate submissions, so the")
    print("   probe measures a state that has already moved.")
    print("both stable and A ~ B -> the instability hypothesis is NOT")
    print("   supported. The probe had a stable target and still missed")
    print("   it, and the failures need a different explanation.")
    print("=" * 74)
    m = out.get("metrics")
    if m:
        print("metered:", m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--retrieve", default=None)
    a = ap.parse_args()

    if a.dry_run:
        n = len(PATCHES) * REPEATS
        print(f"{len(PATCHES)} patches x {REPEATS} repeats = {n} circuits/job")
        print(f"2 jobs x {n} x {SHOTS} = {2*n*SHOTS:,} circuit-shots")
        print(f"projected: {2*n*SHOTS*3.0/3584:.0f} s")
        print("\norder (interleaved):")
        for nm, _, _ in build_named()[:6]:
            print("  ", nm)
        print("   ...")
        print("\nDRY RUN - zero QPU")
        return
    if a.retrieve:
        retrieve(a.retrieve)
        return
    if not a.submit:
        raise SystemExit("choose --dry-run, --submit, or --retrieve")

    print("Q-E STABILITY TEST. This SPENDS QPU TIME (two jobs).")
    if input("type SUBMIT to proceed: ").strip() != "SUBMIT":
        raise SystemExit("aborted")
    jf = submit()
    print("\nwaiting for job B (Ctrl+C safe)...")
    time.sleep(5)
    retrieve(jf)


if __name__ == "__main__":
    main()
