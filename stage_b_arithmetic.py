"""Stage B sizing arithmetic, derived ONLY from the measured Stage A cost.

Prereg v3 section 6 fixes the formula; this shows the numbers going into
it so they can be checked before anything is submitted.
"""
# ---- MEASURED (Stage A, job d9r5g4pdsedc73ag7hmg, ibm_fez) -------------
PILOT_CIRCUITS = 7
PILOT_SHOTS    = 512
PILOT_SECONDS  = 3.0            # bss = usage = 3, status complete

sec_per_cs = PILOT_SECONDS / (PILOT_CIRCUITS * PILOT_SHOTS)
print("MEASURED ANCHOR (Stage A)")
print(f"  {PILOT_CIRCUITS} circuits x {PILOT_SHOTS} shots = "
      f"{PILOT_CIRCUITS*PILOT_SHOTS:,} circuit-shots in {PILOT_SECONDS}s")
print(f"  -> {sec_per_cs*1e6:.3f} s per 1e6 circuit-shots\n")

# ---- Stage B session, per Amendment A2 section 4 -----------------------
N_CAND      = 8       # candidate patches probed
PROBE_CIRC  = 3       # readout|0>, readout|1>, syndrome
PROBE_SHOTS = 256
POLICIES    = 3       # P-probe, P-archive, P-generic
CLASSES     = 3       # BARE, ENC_PASSIVE, ENC_ACTIVE
STATES      = 2
BARE_QUBITS = 3       # BARE runs on all three data qubits
MAIN_SHOTS  = 4096

probe_cs = N_CAND * PROBE_CIRC * PROBE_SHOTS
main_circ = POLICIES * STATES * ((CLASSES - 1) + BARE_QUBITS)
main_cs  = main_circ * MAIN_SHOTS
total_cs = probe_cs + main_cs

print("STAGE B SESSION")
print(f"  probe : {N_CAND} patches x {PROBE_CIRC} circuits x {PROBE_SHOTS} "
      f"shots = {probe_cs:,} circuit-shots")
print(f"  main  : {main_circ} circuits x {MAIN_SHOTS} shots = {main_cs:,}")
print(f"  total : {total_cs:,} circuit-shots\n")

est_s = total_cs * sec_per_cs
print("PROJECTED COST (linear in circuit-shots from the measured anchor)")
for n in (3, 4, 6, 8):
    print(f"  {n} sessions: {est_s*n/60:6.2f} min "
          f"({est_s:.1f} s per session)")

CAP = 40.0
print(f"\nBudget cap {CAP} min; Stage A spent {PILOT_SECONDS/60:.2f} min.")
print(f"Headroom at 4 sessions: {CAP - PILOT_SECONDS/60 - est_s*4/60:.1f} min")
print("\nSafety factor check -- what if the true rate is worse than measured?")
for mult in (1, 3, 10):
    per = est_s * mult / 60
    afford = int((CAP - PILOT_SECONDS/60) // per)
    verdict = "4 sessions fit" if afford >= 4 else f"only {afford} sessions fit"
    print(f"  {mult:2d}x anchor: {per:5.2f} min/session -> {verdict}")
print("\nBINDING: after session 1, re-read the meter. If the measured cost")
print("exceeds 3x this projection, stop and re-size before session 2.")
