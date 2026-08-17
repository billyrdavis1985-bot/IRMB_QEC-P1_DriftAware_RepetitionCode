# IRMB QEC-P1 — Staged Preregistration (DRAFT v3 — not yet committed)

**Title:** Drift-Aware Repetition-Code Break-Even and Policy Pilot
**Subtitle:** A staged, preregistered pilot estimating the effect of a
rolling longitudinal-archive patch-selection policy versus a
current-snapshot policy on logical bit-flip error, distance-3 repetition
code, ibm_fez.

**Investigator:** Billy R. Davis Jr., Hudson Forge Technologies (IRMB)
**Status:** DRAFT v3. Council disposition on v2: "major-minor revision."
This version implements all six required changes. Commit Stage A before
the engineering pilot; commit Stage B before confirmatory hardware.

**Study class (PI decision, per council fork): PILOT ESTIMATION STUDY.**
Q-A estimates the policy effect and its heterogeneity across windows. It
makes NO confirmatory superiority claim — the sign-test arithmetic shows
3-5 windows cannot support one. Confirmatory testing is deferred to a
future QEC-P2 designed from this pilot's estimates.

---

## 0. Verified preconditions and constraints

- ibm_fez target exposes if_else, measure, reset (checked 2026-08-04).
  Control-flow restrictions apply: no nested conditionals; no measurement
  or reset inside conditional branches. All circuits must respect these.
- Basis gates identical to QNN-P1; scorer and transpile checks port.
- **Execution mode: [VERIFY before Stage A commit] Open-plan accounts
  cannot submit Session workloads; paired conditions run "paired and
  randomized within the same packed job or IBM Batch, per the verified
  execution mode available to this account." Session language is removed
  throughout.**
- Budget: ~140 QPU-min remaining. **Hard cap for QEC-P1: 40 min total
  (pilot + all windows). Remainder reserved for Design 6.**
- Archive: hourly ibm_fez snapshots (Drift Collector), ~Jun 2026-present.
  **Unit of archive analysis: unique calibration cycles (distinct
  calibration timestamps), never raw hourly snapshots.**

---

## 1. Questions and claims

**Q-A (policy, estimation only):** What is the paired difference in
logical bit-flip error between the rolling-archive policy and the
current-snapshot policy, and how heterogeneous is it across calibration
windows? Reported as estimates with intervals. No superiority claim.

**Q-B (break-even characterization):** Where does the d=3 bit-flip code
sit relative to break-even on this device, and does patch choice move
that boundary? S<1 is a pre-declared informative outcome.

**Claim boundary:** any suppression statement refers exclusively to
logical bit-value (X-channel) error in a computational-basis memory on
this code and device. No "protected logical qubit" claim under any
outcome. |0_L> and |1_L> reported separately before averaging.

---

## 2. Prior work (placeholders resolved per council)

No novelty claimed over:
- Stein et al., arXiv:2601.16123 (calibration-conditioned FiLM decoders;
  352 hardware snapshots, d=3-11, both bases, three IBM processors).
- Bhardwaj, Takou, Lin & Brown, arXiv:2511.09491 (sliding-window
  estimation of drifting Pauli noise from syndromes).
- Tannu & Qureshi, "Not All Qubits Are Created Equal," **ASPLOS 2019**
  (52-day variability-aware allocation).
- Murali et al., "Noise-Adaptive Compiler Mappings," ASPLOS 2019,
  arXiv:1901.11054.
- Drouet et al., arXiv:2607.12118 (defect-exclusion vs defect-aware,
  distance-5 surface code).
- Czabán et al., arXiv:2606.30606 (repetition-code readout-error coding
  across platforms — adjacent, not identical).
- Liepelt, Peduzzi & Wootton 2024 (standardized repetition-code
  benchmarking).
- IBM dynamic-circuit/repetition-code tutorials and Heron benchmarks.
  [Action: read before Stage A commit; calibrate S expectations.]

**Contribution:** a prospective, paired, multi-window PILOT estimating
whether a frozen rolling longitudinal-stability policy selects patches
that differ from — and outperform — a frozen snapshot-only policy, on
logical bit-flip error with duration-matched physical baselines,
preregistered decision rules, independent telemetry, immutable records,
consumer infrastructure. Fresh literature search in commit week.

---

## 3. Design

### 3.1 Code and rounds
d=3 bit-flip repetition code (3 data + 2 ancilla). **Syndrome rounds:
3 (frozen).** Ancilla reset between rounds via measurement-conditioned X
(IBM tutorial pattern), respecting the no-reset-in-branch restriction.

### 3.2 Patch-selection policies

Both policies share: identical 5-qubit patch topology constraints
(ancillas coupled to their data pairs), zero-SWAP requirement, identical
circuits, transpilation settings, rounds, states, shots.

- **P-archive — ROLLING policy (PI decision):** the ALGORITHM is frozen,
  not one patch. Before each window it consumes all unique calibration
  cycles available up to selection time. Score = frozen weighted
  combination of instantaneous base-quality terms (T1, T2, readout
  error, data-ancilla CZ error) PLUS temporal aggregation: historical
  mean, variance penalty, worst-tail penalty, missing-data penalty.
  Weights, normalization, and tie-breaking frozen at Stage A commit.
- **P-today:** the SAME instantaneous base-quality terms computed from
  only the latest eligible unique calibration cycle. No temporal terms
  (a single snapshot cannot produce them — v2 wording corrected).
  Maximum snapshot age at selection: [declared at Stage A commit].

**Timing semantics (SUBMISSION-TIME policy, frozen):** both policies
select from information available immediately before job submission.
Recorded per window: selection timestamp, calibration timestamp used,
submission timestamp, job-start timestamp, end timestamp, delay, and
whether recalibration occurred while queued.
**Pre-declared recalibration rule:** if the backend recalibrates between
selection and execution start, the window REMAINS a valid test of the
submission-time policy (that is the operational reality any user faces)
and is flagged; flagged-window sensitivity analysis is reported.

**Convergence rule:** if both policies select the same patch in a
window, record policy convergence; the window executes once and informs
Q-B only. Convergent windows contain no policy contrast and are excluded
from the Q-A paired estimate (they are reported as convergence-rate
data). "Low intervention distinctness" language is used; convergence is
not itself evidence the archive lacks value.

P-generic (transpiler default at optimization_level=3, no
initial_layout) and P-weak (lowest-scoring valid patch): Tier 1
simulation controls only. No confirmatory hardware budget.

### 3.3 Hardware circuit classes

1. **BARE:** duration-matched single-qubit memory (delays matched to the
   encoded circuit's schedule, same DD setting). **Executes on ALL THREE
   data qubits of the active patch** (council: a measured mean requires
   measuring all three). Primary baseline = the constituent designated
   BEFORE execution by the frozen patch score (highest-scored data
   qubit). Secondary = arithmetic mean of the three measured bare rates.
   Lowest measured bare rate may be reported as post-outcome descriptive
   only, labeled as such. BARE is a matched-memory comparator, not an
   exact overhead-free counterfactual — stated in all reporting.
2. **ENC-PASSIVE:** encoded, 3 syndrome rounds, no in-circuit
   correction. Analysis variants from the same records: raw; final-data
   majority; offline syndrome-decoded; postselected (all syndrome bits
   zero in all rounds; one anomalous round rejects); acceptance-adjusted
   utility.
3. **ENC-ACTIVE:** encoded, 3 rounds, per-round if_else correction from
   that round's syndrome, ancilla reset between rounds.

**Decoder specification (frozen, complete):** per-round syndrome
(s1,s2) → correction: (0,0)→I; (1,0)→X on d1; (1,1)→X on d2; (0,1)→X on
d3. ENC-ACTIVE applies this in-circuit each round. The OFFLINE decoder
applies the same table sequentially in software over the recorded
3-round syndrome history (mirroring the active path), then final-data
majority. This exact map is the decoder; "majority vote" alone is
retired as underspecified. Tier 0 must verify every syndrome history in
{0,1}^6 decodes deterministically per this rule.

**DUMMY-FF diagnostic (validity self-verifying):** same syndrome
measurement and conditional branch structure, with a conditional
operation chosen so the transpiled, scheduled circuit provably retains
the conditional-control path and comparable timing (verified by
inspecting the transpiled circuit and schedule). If no such neutral
operation survives transpilation without being optimized away, DUMMY-FF
is DROPPED and the latency question is answered observationally via E4.
No sixth qubit; patch topology is not modified for the diagnostic.

### 3.4 Functional verification
Injected-X tests (each data qubit, declared position) verify the
syndrome table on hardware during the Stage A pilot. Engineering data,
never pooled with confirmatory results.

### 3.5 Replication structure
Unit of replication: calibration window (distinct calibration cycle,
verified by timestamp change between windows). **Target: 4 windows;
minimum 3; each window pairs both policies (when discordant), all
circuit classes, both logical states, interleaved within one packed
job/batch.** Per the pilot-study class, windows support estimation and
heterogeneity description only. If fewer than 2 discordant windows
occur, Q-A is reported as convergence-dominated (see §9).

### 3.6 Frozen at Stage A commit
Shots per condition (set by pilot arithmetic); inter-round spacing; DD
on idle data qubits [on/off decision]; rep_delay; initialization; barrier
placement; transpiler optimization level, seed, layout enforcement;
archive cutoff and eligibility rules; score weights; max snapshot age.

### 3.7 Out of scope
d>3; MWPM/neural decoding; syndrome-derived noise estimation; phase
protection; leakage measurement or postselection (bitstrings are not a
leakage detector; NO leakage claim of any kind).

---

## 4. Staged preregistration (council's required structure)

**STAGE A — Engineering-pilot preregistration (commit BEFORE pilot):**
freezes: exact pilot circuits (all three classes + DUMMY-FF + injected-X
on ONE diagnostic patch), the diagnostic patch selection rule, pilot
shots, budget ceiling for the pilot, amendment procedure.
**Diagnostic patch = the third-ranked patch under P-archive scoring**
(deliberately excluded from likely confirmatory selections, per council).
**Allowed pilot outputs:** quantum_seconds/metered cost; transpilation
success and transpiled-circuit properties; result schema; circuit
duration; job/subjob structure; reset and control-path execution
success; injected-X decode correctness.
**Forbidden before Stage B commit:** computing, inspecting, or comparing
policy-level or patch-level logical error rates from pilot data; any
p_L beyond the injected-X pass/fail; any S estimate.

**STAGE B — Confirmatory amendment (commit BEFORE window 1):** using
Tier 1 outputs and pilot COST data only, via the fixed formula in §6:
shots per condition, number of windows, the frozen matrix, the
statistical model, numeric G3 evaluation. Timestamped amendment appended
to this file.

---

## 5. Metrics

**Logical failure:** decoded logical outcome ≠ prepared state.
**Estimand (Q-A):** Δ_policy = p_L(P-archive) − p_L(P-today), paired by
window, ENC-ACTIVE, per logical state. Negative favors the archive.
**Primary effect measure:** absolute risk difference. **Secondary:**
S = p_BARE / p_L.
**SESOI (PI decision, set now, before Tier 1): δ = 0.010** — a one
percentage-point absolute reduction in logical error is the smallest
effect of operational interest, justified by: (a) at ~8+ min/window of
QPU, a sub-1pt improvement does not repay the archive's operational
complexity for Design 6 qualification use; (b) sub-1pt differences are
implausible to resolve within the 40-min cap per the council's power
table. [PI may revise ONLY at Stage A commit, never after Tier 1.]
**MDE:** computed at Stage B from measured cost, acceptance, windows,
clustering — a property of the design, NOT a success threshold.
**Intervals:** Wilson per cell; paired-by-window analysis for Q-A.
**Multiplicity:** ONE primary estimate (Q-A on ENC-ACTIVE, |1_L>, the
more damping-exposed state); all else secondary/exploratory.
**Postselection reporting rule:** conditional p_L NEVER without
acceptance rate, unconditional success per submitted shot, and
QPU-seconds per successful logical outcome.

---

## 6. Endpoints

- **E1 (Q-A, estimation):** paired Δ_policy across discordant windows,
  point estimate + interval + per-window values + heterogeneity
  description. Interpretation frame: |Δ| ≥ SESOI and interval excluding
  zero = "pilot evidence of an operationally relevant policy effect,
  motivating confirmatory QEC-P2"; anything less = estimated as
  observed, no strength language.
- **E2 (Q-B):** S per class per policy, classified S>1 / S≈1 / S<1 with
  pre-stated interpretations; no success language unless S>1 with
  interval excluding 1.
- **E3 (model validation, secondary, non-gating):** Tier 1 → hardware
  p_L gap per condition.
- **E4 (feedforward):** p_L(ENC-ACTIVE) vs p_L(ENC-PASSIVE, offline
  decoder, all shots) — the fair comparison; DUMMY-FF penalty if the
  diagnostic validates. **A feedforward penalty is
  p_L(ENC-ACTIVE) > p_L(ENC-PASSIVE-offline)** (v2 sign error
  corrected). Cause attribution only as diagnostics support: candidate
  causes include syndrome measurement error, correction-map error,
  extra X-gate error, reset failure, idle decoherence, transpilation
  differences, leakage, control latency.

**Stage B fixed formula (frozen now):** shots_per_condition and
window_count = the maximum satisfying [total_cost(measured per-window
cost) ≤ 40 min − pilot spend] with shots allocated equally across
conditions and windows ≥ 3; MDE then computed from that allocation with
the acceptance rate measured in Tier 1 postselection simulation.

---

## 7. Pre-hardware gates (free; any failure stops hardware)

**G1 — Intervention distinctness (FIRST):** over ≥10 held-out UNIQUE
calibration cycles: policy disagreement rate; patch-overlap rate;
first-vs-second-rank score margins; expected discordant windows within
budget; Tier 1-estimated |Δ_policy| during discordant cycles. GATE: the
policies must disagree often enough, and with large enough expected
consequence, that ≥2 discordant windows are expected within the 4-window
budget AND expected |Δ| during discordance is ≥ SESOI/2. Otherwise:
reframe per §9 before further work. (The v2 fixed 70% threshold is
retired as arbitrary.)

**G2 — Tier 0 correctness:** all 64 syndrome histories decode per §3.3;
injected-X cases correct; ideal p_L ≈ 0.

**G3 — Tier 1 policy resolution (envelope, not point estimate):** across
a simulation ENVELOPE — optimistic/nominal/pessimistic measurement,
reset, and latency variants × multiple held-out cycles × stale-snapshot
scenarios — if expected |Δ_policy| < attainable MDE under ALL plausible
variants, Q-A stops (reported as unresolvable). Variant disagreement is
reported as model uncertainty, not resolved by picking the favorable
variant. NOT a kill criterion: absence of S>1 (Q-B proceeds regardless).

**G4 — Discriminant validity:** if P-weak does not underperform in Tier
1, the patch score lacks demonstrated discriminant validity for this
workload; Q-A pauses until diagnosed or dropped. (Not auto-attributed to
simulator error — candidate causes include score-weight mismatch,
readout/CZ trade-offs, scheduling artifacts, insensitive outcome.)

**G5 — Compile gate:** every exact circuit transpiles against the live
target with declared layout, zero SWAPs, no unsupported control flow,
conditionals preserved — verified before the Stage A pilot.

---

## 8. Cost pilot = Stage A execution
Per §4. Meter read after; Stage B arithmetic shown in the amendment.
Job IDs to disk before any wait. No inherited cost figures.

---

## 9. Pre-declared branches
- **G1 fails / convergence-dominated (<2 discordant windows):** study
  becomes "policy convergence + break-even characterization"; Q-A
  reported as convergence data; Q-B proceeds on the converged patch.
- **G3 fails:** Q-A reported unresolvable at this budget; Q-B may
  proceed under reduced scope or stop.
- **Feedforward penalty (E4 positive):** reported as latency/overhead
  characterization with diagnostic-supported attribution only.
- **Pilot reveals cost > budget for ≥3 windows:** study stops at Stage A
  with the cost model as its published result (an honest infrastructure
  finding), or PI amends the cap by pre-declared amendment.

---

## 10. Guardrails
All v2 guardrails retained, plus: staged-commit integrity (no policy-
level analysis of pilot data before Stage B); calibration captured
before AND after each window; execution-mode language matches verified
account capability; single-window results carry no stability claim;
convergent windows never counted as policy evidence; deviations logged
live.

---

## 11. Deviations log
(Live.)

## 12. Open items before Stage A commit
- [ ] Verify account execution mode (job/batch vs session)
- [ ] Read IBM Heron dynamic-circuit/repetition-code benchmarks
- [ ] Read Stein + Bhardwaj methods in full; fresh literature search
- [ ] Implement G1 on unique calibration cycles; run it
- [ ] Fix §3.6 values; DD decision; snapshot-age limit
- [ ] Tier 0 build + G2 pass
- [ ] G5 compile gate pass
- [ ] PI confirms: pilot-path class, rolling P-archive, SESOI = 0.010
- [ ] Commit Stage A
## Amendment A1 (2026-08-06) — patch score re-weighting after Tier 1
### Pre-declared BEFORE any re-run; no hardware has been executed.

**Status of the study at this amendment:** zero QPU seconds spent. Gates
G1 and G2 passed. Tier 1 completed (394/432 cells, 8.8% Aer crash rate).
Everything below is a simulation-stage design change made under the
section 9 reframing branches.

---

### 1. What Tier 1 found

The rolling-archive policy was consistently WORSE out of sample than the
current-snapshot policy: mean paired delta positive in all six
variant/state combinations (optimistic +0.0020/+0.0028, nominal
+0.0056/+0.0057, pessimistic +0.0144/+0.0161), archive-better in 1 of 35
paired comparisons.

G4 failed in the same run: P_weak underperformed in only 48% of
comparable cells, indicating the patch score itself could not reliably
separate good patches from bad ones.

### 2. Why (the discriminant-validity diagnosis)

Spearman correlation of each scoring feature against measured logical
error, over 131 completed ENC_ACTIVE cells:

| feature | pooled rho | direction |
|---|---|---|
| readout_sum | **+0.607** | correct, dominant (+0.83 to +0.91 in every variant/state cell) |
| cz_err_sum | +0.344 | correct |
| inv_T1_sum | +0.306 | correct |
| inv_T2_sum | +0.271 | correct |
| hist_mean | +0.288 | correct |
| **hist_variance** | **-0.114** | **anti-predictive** |
| **hist_tail** | **-0.188** | **anti-predictive** |
| COMPOSITE_today | +0.282 | weak but valid |
| COMPOSITE_archive | **-0.114** | **no discriminant validity** |

The two archive-only temporal penalties are negatively correlated with
logical error in ALL six variant/state cells. They steer selection away
from low-readout patches, and readout is the dominant predictor for a
repetition code whose ancillas are measured every round.

**Conclusion:** the Tier 1 result does not falsify longitudinal
calibration information. It falsifies THIS temporal weighting. The
archive composite was actively anti-predictive (rho = -0.114), so the
archive-vs-today comparison was argmin over a function that did not track
the outcome.

### 3. The change

**3a. Instantaneous terms re-weighted, rho-proportional and
scale-corrected.** Each feature's weight is set so its contribution at
typical fez values is proportional to its measured |rho|:

    W_READOUT = 100.0     (was 1.0)
    W_CZ      = 327.0     (was 10.0)
    W_T1      = 115.0     (was 50.0)
    W_T2      = 75.0      (was 50.0)

Typical-value contributions become readout 6.00, cz 3.40, T1 3.02,
T2 2.68 -- readout dominant, matching the measurement.

**3b. Anti-predictive temporal penalties removed.**

    W_VAR  = 0.0          (was 2.0)   -- rho -0.114
    W_TAIL = 0.0          (was 1.0)   -- rho -0.188

**3c. P-archive is redefined as the historical MEAN of the re-weighted
instantaneous score** (hist_mean, rho +0.288, the one temporal feature
that predicts in the correct direction), plus the unchanged missing-data
penalty (W_MISSING = 5.0). The policy contrast therefore becomes:

    P-today   : re-weighted score on the latest eligible cycle
    P-archive : mean of the re-weighted score over all prior eligible
                cycles (rolling, causal, algorithm frozen)

This is now a clean test of "does averaging over history beat using the
most recent snapshot," with no anti-predictive terms in either arm.

### 4. Circularity control (binding)

The new weights were derived FROM Tier 1 outcomes. The 131 cells used in
the diagnosis are therefore TRAINING data and cannot also serve as the
test.

Binding commitments:
1. G1 and Tier 1 are re-run from scratch under the new weights.
2. The prior Tier 1 result and the diagnosis are reported in full as the
   derivation, never as evidence for the re-weighted score.
3. If the re-weighted archive policy wins, that result is labelled
   **exploratory** unless it is confirmed on calibration cycles collected
   AFTER 2026-08-06, which no part of the weight derivation could have
   seen. The collector continues running, so those cycles accrue
   automatically.
4. G4 is re-evaluated as the validity gate. If P_weak still fails to
   underperform under the new weights, the score is still not valid for
   this workload and Q-A does not proceed to hardware.

### 5. What does NOT change

SESOI (0.010); the pilot-estimation study class; the staged Stage A /
Stage B structure; the frozen decoder and syndrome table; the three
hardware circuit classes; the 40-minute QPU cap; all section 10
guardrails; and every endpoint definition. No hardware decision is
affected by this amendment because no hardware has run.

### 6. Deviation logged

Aer native crashes (exit -1073741819 / SIGSEGV) occur non-
deterministically during Tier 1 simulation. Established as
input-independent: reproduced on Windows and Colab Linux, on physically
valid calibration values, with and without dynamic circuits, and a
condition that crashes in sequence passes when run first in a fresh
process. Mitigated by per-condition process isolation
(qec/tier1_runner.py); crashed cells are recorded with exit codes and
excluded from analysis. Crash rate for the completed Tier 1 sweep: 8.8%
(38 of 432 cells). Affected keys are preserved in
runs/tier1_heldout.json.
## Amendment A2 (2026-08-06) — Path B: probe-vs-passive selection and
## independent validation of the DAQEC crossover threshold
### Pre-declared BEFORE any hardware execution. Zero QPU spent to date.

---

### 1. Why the study is being redirected

Tier 1 (twice, under two independently derived scoring functions) found
that patch selection from **passive archived calibration metadata** does
not reduce logical error, and G4 failed both times: the score could not
reliably separate P_weak from the selected policies.

Two published results from Ashuraliyev (independent researcher, Tashkent)
explain this and reframe the question:

**(i) DAQEC-Benchmark** (Zenodo 10.5281/zenodo.18045662; manuscript
submitted to Nature Communications). 756 QEC runs, 126 paired
probe-deploy sessions, repetition code d=3-11 on IBM hardware. Reports
60% logical error reduction (probe-deploy 0.0018 +/- 0.0001 vs baseline
0.0045 +/- 0.0002), 76-77% tail reduction, p < 0.01, across 3 backends
and 14 days. **Their selection ranks candidates by MEASURED error from
30-shot probe circuits, not by calibration metadata.**

**(ii) "Hardware Noise Level Moderates Drift-Aware QEC"** (Research
Square rs-8475008, 2026-02-19). Finds a crossover: adaptive selection
degrades LER by 14.3% below baseline LER 0.112 and improves it by 8.3%
above (r = 0.71, P < 1e-11, IBM Torino, N=69 + N=15 pairs). Mechanistic
decomposition: 15.4% fixed overhead vs 23.1% drift-signal benefit;
Benefit(%) = 857.8 x LER - 96.0, R^2 = 0.50.

**Consequence for QEC-P1.** Simulated ENC_ACTIVE logical error rates in
our Tier 1 sweep were 0.001-0.03 — one to two orders of magnitude BELOW
the reported 0.112 crossover. Under their model, selection strategies
cannot help in that regime because there is nothing to optimize. This is
an independent quantitative explanation for both our negative policy
result and our G4 failure, and it is testable rather than merely
plausible.

**One tension we do not paper over.** Our archive penalty GREW with
modelled noise (+0.0010 optimistic, +0.0052 nominal, +0.0150
pessimistic), whereas their model predicts adaptive selection improves as
noise rises. The comparisons differ (ours: longitudinal vs instantaneous
metadata; theirs: measured-probe vs calibration baseline), but the
direction conflict is recorded here as a pre-declared point of interest,
not resolved by assumption.

---

### 2. Revised questions

**Q-A' (primary, estimation).** Does selection from a short MEASURED
probe outperform selection from passive archived calibration, and does
either outperform a generic layout, on the same code and device?
Three policies, paired within session:

| policy | selection rule |
|---|---|
| P-probe | rank candidates by measured readout/logical error from short probe circuits, deploy the best |
| P-archive | rolling frozen archive score (Amendment A1 weights), no probe |
| P-generic | transpiler default layout, optimization_level=3, no initial_layout |

**Q-B (retained).** Break-even characterization: S = p_BARE / p_L across
BARE / ENC_PASSIVE / ENC_ACTIVE, duration-matched.

**Q-C (new, threshold validation).** Where does the crossover sit on
ibm_fez at d=3? The source publication states its threshold "was derived
from the same dataset used to demonstrate the interaction effect and
should be treated as an empirical estimate rather than a pre-registered
hypothesis," and that "independent validation of the exact threshold
value on held-out hardware remains for future work." Their model predicts
IBM Heron d=3 crossover at LER 0.18-0.22.

**Pre-declared analysis for Q-C:** regress (p_L[P-probe] -
p_L[P-generic]) on baseline p_L[P-generic] across sessions; report the
x-intercept with a bootstrap CI. **This is an estimation study.** With
the session counts a 40-minute budget supports, it cannot confirm or
refute their threshold; it reports an independent point estimate and its
uncertainty, and states plainly whether the sign pattern is consistent.

---

### 3. Prior-work positioning (binding)

QEC-P1 claims NO novelty over: probe-based drift-aware selection
(Ashuraliyev, DAQEC-Benchmark), the noise-level interaction effect
(Ashuraliyev rs-8475008), calibration-conditioned neural decoding (Stein
et al. arXiv:2601.16123), syndrome-derived drift estimation (Bhardwaj et
al. arXiv:2511.09491), variation-aware qubit allocation (Tannu & Qureshi,
ASPLOS 2019), noise-adaptive compilation (Murali et al., ASPLOS 2019), or
syndrome-derived device benchmarking (Wootton, arXiv:2207.00553).

**Claimed contribution, narrow:** (a) a preregistered head-to-head of
measured-probe vs passive-archive selection, which the prior work does
not run as a contrast; (b) an independent point estimate of the crossover
on a different device (ibm_fez) and code distance than the source
dataset; (c) a documented negative on passive-metadata selection with the
discriminant-validity mechanism (Spearman feature analysis, Amendment
A1).

**Source caveats recorded before use:** rs-8475008 is an unrefereed
preprint; single author; the threshold is self-admittedly post-hoc from
the demonstrating dataset; reported Ns are internally inconsistent
(N=15 in text vs N=48 in figure panels); and the ibm_fez validation rests
on 6 executions. The crossover is treated here as a HYPOTHESIS TO TEST,
never as an established constant.

---

### 4. Design

**Code and circuits.** Unchanged from v3 section 3: d=3 bit-flip
repetition code, 3 rounds, frozen syndrome table and decoder, three
hardware circuit classes (duration-matched BARE on all three data qubits,
ENC_PASSIVE, ENC_ACTIVE), both logical states reported separately.

**Probe design (adopted from the source protocol, cited).** Short probe
circuits over N candidate patches; candidates ranked by MEASURED error;
best deployed. Probe shot count and candidate count are frozen at Stage A
after the pilot measures their cost. The source used 30-shot probes over
9-qubit chains at d=5; we use d=3 patches, so probe parameters are set by
our own pilot, not inherited.

**Session structure.** Within one session, all three policies execute
paired and interleaved in randomized order, all circuit classes, both
states. Randomization seed recorded. Calibration timestamp captured
before AND after each session.

**Replication.** Target 4 sessions across distinct calibration windows;
minimum 3. Sessions are the unit of replication. **Study class remains
PILOT ESTIMATION** — no confirmatory superiority claim, per the sign-test
arithmetic in v3.

---

### 5. Budget (arithmetic shown, not assumed)

Per session: probes (30 shots x 8 candidates = 240) + main grid
(4096 shots x 3 classes x 2 states x 3 policies = 73,728) = ~73,968
circuit-shots.

Extrapolating from the ONLY measured anchor we have (QNN-P1: 1,638,400
circuit-shots = 8 QPU-min on ibm_fez):

| assumption | per session | 4 sessions |
|---|---|---|
| QNN-P1 rate holds | ~0.4 min | ~1.4 min |
| 3x (mid-circuit + dynamic overhead) | ~1.1 min | ~4.3 min |
| 10x | ~3.6 min | ~14.4 min |

**These are extrapolations from a different circuit class and are NOT
used to size the study.** Stage A measures the real per-session cost;
Stage B fixes shots and session count from that measurement by the frozen
formula in v3 section 6. Hard cap unchanged: **40 QPU-minutes total**,
remainder reserved for Design 6.

---

### 6. Gates

- **G5 (compile)** — unchanged, still outstanding: every exact circuit
  transpiles against the live target with declared layout, zero SWAPs,
  no unsupported control flow, conditionals preserved. Heavy-hex max
  degree is 3, so flag-qubit requirements (cf. arXiv:2403.10217) must be
  ruled out at transpile time for every candidate patch.
- **G6 (new, probe validity)** — the probe must rank candidates better
  than chance against the same session's measured main-run p_L. If probe
  rank and deployed p_L are uncorrelated across candidates, the probe arm
  has no discriminant validity and Q-A' reports that, exactly as G4
  reported it for the passive score. **This is the same gate that caught
  the passive score; it is applied to the new method too.**
- **G1/G2** — passed; carried forward unchanged.
- **G3/G4 (simulation gates)** — retired for Q-A'. Tier 1 has served its
  purpose: it produced the negative and the mechanism. The probe arm
  cannot be evaluated in simulation, because a simulated probe measures
  the simulator's own noise model rather than the device.

---

### 7. Retained without change

SESOI (0.010); staged Stage A / Stage B commit structure with the
forbidden-analyses list; frozen decoder and syndrome table; postselection
reporting rules (conditional p_L never without acceptance rate and cost
per success); absolute risk difference primary, suppression ratio
secondary; every section 10 guardrail; the Aer crash deviation and its
process-isolation mitigation.

---

### 8. Deviation record addition

Tier 1 was run twice (2026-08-06). First run: original weights, 394/432
cells, 8.8% Aer crash rate. Second run: Amendment A1 weights, 395/432
cells, 8.6% crash rate. Both produced the same directional result. Score
diagnosis over 131 ENC_ACTIVE cells is retained as the derivation record
for A1 and is explicitly NOT evidence for the re-weighted score.
## Stage B Commit (2026-08-07) — confirmatory matrix frozen
### Committed BEFORE any confirmatory session. Stage A is complete.

Per PREREGISTRATION v3 section 4, this amendment fixes the confirmatory
design using ONLY (a) Tier 1 simulation outputs and (b) Stage A COST
data. No patch- or policy-level logical error rate from the pilot was
computed or inspected; the forbidden-analysis guard in qec/stage_a.py
enforced this in code.

---

### 1. Stage A outcome (allowed outputs only)

Job d9r5g4pdsedc73ag7hmg, ibm_fez, diagnostic patch (140,141,142,143,144),
7 circuits x 512 shots.

| allowed output | value |
|---|---|
| metered cost | bss 3 s, usage 3 s, status complete |
| readout probe \|0> | [0.00977, 0.00586, 0.00195, 0.0, 0.04688] |
| readout probe \|1> | [0.03125, 0.00977, 0.00195, 0.01172, 0.0332] |
| syndrome false-detection rate | 0.08008 |
| control path executed | yes (78 distinct outcomes, ENC_ACTIVE) |
| injected-X decode | p_L = 0.1582, corrected = True |

The injected-X check is the one sanctioned p_L in Stage A (functional
verification). It confirms the frozen syndrome table and the in-circuit
correction path behave correctly on hardware, not only in simulation.

**Note for interpretation, not a result:** the 8.0% syndrome
false-detection rate on an error-free state means a non-trivial fraction
of rounds will trigger a false correction, and false corrections inject
errors. This makes Q-B's break-even question materially live. It is
recorded here as an observation from an allowed Stage A output; it is not
used to set any threshold.

---

### 2. Frozen confirmatory matrix

Derived from the measured anchor (3,584 circuit-shots = 3.0 s, i.e.
837 s per 1e6 circuit-shots) by the formula frozen in v3 section 6.

**Per session:**

| component | value |
|---|---|
| candidate patches probed | 8 |
| probe circuits per candidate | 3 (readout \|0>, readout \|1>, syndrome) |
| probe shots | 256 |
| policies | 3 (P-probe, P-archive, P-generic) |
| circuit classes | BARE (x3 data qubits), ENC_PASSIVE, ENC_ACTIVE |
| logical states | 2 (\|0_L>, \|1_L>) |
| main shots | 4096 |
| main circuits | 3 policies x 2 states x 5 = 30 |
| **session total** | **129,024 circuit-shots, ~108 s projected** |

**Sessions:** 4 target, 3 minimum, each in a distinct calibration window
(verified by calibration timestamp change). Within a session all
policies execute paired and interleaved in randomized order; the
randomization seed is recorded.

**Projected total: ~7.2 min of the 40-min cap.** Headroom ~33 min.

**Binding cost rule:** after session 1, re-read the meter. If measured
cost exceeds 3x the projection (>5.4 min for one session), STOP and
re-size by amendment before session 2. At 10x the anchor only 2 sessions
would fit, so this rule is what prevents silently overrunning.

---

### 3. Frozen analysis model

- **Primary estimand (Q-A'):** paired within-session difference in p_L,
  ENC_ACTIVE, \|1_L>, between P-probe and P-archive. Absolute risk
  difference. Negative favours P-probe.
- **Secondary:** P-probe vs P-generic; P-archive vs P-generic; both
  logical states reported separately before any averaging.
- **Q-B:** S = p_BARE / p_L per class per policy, with p_BARE from the
  pre-designated best constituent data qubit (frozen by score before
  execution) and also reported against the mean of all three.
- **Q-C:** regress (p_L[P-probe] - p_L[P-generic]) on baseline
  p_L[P-generic] across sessions; report x-intercept with bootstrap CI.
  **Estimation only** — 4 sessions cannot confirm or refute the published
  0.112 threshold, and no such claim will be made.
- **Intervals:** Wilson per cell; paired-by-session for the primary.
- **Multiplicity:** ONE primary comparison; all else exploratory.
- **Postselection:** conditional p_L never reported without acceptance
  rate, unconditional success per submitted shot, and QPU-seconds per
  successful logical outcome.
- **SESOI:** 0.010, unchanged, set before Tier 1 and never revised.
- **Study class:** PILOT ESTIMATION. No confirmatory superiority claim.

---

### 4. G6 — probe validity (evaluated per session)

Spearman rank correlation between probe score and measured main-run p_L
across the candidate patches deployed. Thresholds as declared:
rho >= 0.4 valid, 0.2-0.4 weak, < 0.2 fail.

If G6 fails, Q-A' reports that the probe lacks discriminant validity for
this workload — exactly as G4 reported it for the passive archive score.
A published positive result elsewhere does not exempt the probe from the
gate that killed the passive method.

---

### 5. Deviation log entry

**D-A1 (2026-08-07).** The Stage A analysis pass initially reported
injected_x_logical_error = 0.9043 (corrected = False) and 4 distinct
outcomes for a 9-classical-bit circuit. Root cause: the result parser
resolved classical registers with getattr on the SamplerV2 DataBin, but
DataBin exposes its own attributes (data, keys, items, values, shape,
size, ndim); the encoded circuits contain a register literally named
"data", so the container attribute was returned instead of the register
and only one 2-bit register was read. Fixed by subscript access
(data[name]). Re-analysis of the SAME job via --retrieve gave 78 distinct
outcomes and injected_x_logical_error = 0.1582 (corrected = True). **Zero
additional QPU was spent on the correction.** No scientific conclusion
was drawn from the erroneous pass. The pilot detecting this before Stage
B is the staged design working as intended.

**D-A2 (2026-08-07).** The first Stage B sizing script printed "4
sessions at 10x = 72.0 min (still inside cap)", which is false against a
40-minute cap. Corrected before use to compute affordable session counts
per multiplier (1x and 3x: 4 sessions fit; 10x: 2 sessions fit).

---

### 6. Unchanged

Frozen decoder and syndrome table; three hardware circuit classes;
duration-matched BARE; both logical states separate; staged-commit
integrity; all section 10 guardrails; the Aer crash deviation and its
process-isolation mitigation; prior-work positioning and source caveats
from Amendment A2 section 3.
## Amendment A3 (2026-08-09) — session replication unit redefined
### Pre-declared BEFORE session 2. Session 1 is complete and unaffected.

---

### 1. The situation

`ibm_fez` last published a calibration update at **2026-08-06 23:21:59-04:00**.
As of 2026-08-09 16:51 that is **~65 hours**, verified with
`properties(refresh=True)` so it is not a client cache. The backend reports
`operational: True`, `status: active`, 0 pending jobs. `ibm_marrakesh` froze
at 2026-08-06 23:19:40, two minutes earlier, so the event is fleet-wide and
not specific to this account or device.

The QPU Drift Collector polled correctly throughout (hourly, `dedup_skip` on
unchanged timestamp, exit 0). Nothing on the collection side failed.

For context from the archive itself: 707 snapshots between 2026-06-18 and
2026-08-06 produced 707 unique calibration timestamps, median gap **1.2
hours**, maximum **60.6 hours**. The present gap exceeds every previously
observed interval.

### 2. Why the original gate was wrong

Stage B required a **changed published calibration timestamp** as the marker
of a distinct session window. That was a proxy for the actual scientific
requirement, which is that sessions sample **different hardware states**.
The proxy fails for two reasons:

**(a) IBM documents that benchmarking can fail for days.** Per IBM's backend
documentation: if benchmarking of a qubit or edge does not succeed over the
course of several days, the reported error value is considered stale and is
reported as 1 — explicitly meaning *undefined*, not *broken*. Multi-day gaps
in published calibration are therefore an anticipated operating condition,
not an anomaly the protocol may assume away.

**(b) `ibm_fez` adjusts itself continuously regardless of publication.**
Heron r2 runs active two-level-system (TLS) mitigation: the system
continuously monitors the TLS environment and makes calibration adjustments
to keep the chip away from TLS resonances. The physical device state
therefore evolves *between* published snapshots. A frozen published
timestamp does not imply frozen hardware; it implies frozen *metadata*.

Taken together: the published timestamp is a poor marker of hardware state,
and gating on it can stall the study indefinitely for a reason unrelated to
the science.

### 3. The change

**Replication unit (revised).** A session is a distinct window if it is
separated from the previous session by **at least 12 hours**. The published
calibration timestamp is still recorded before and after every session, and
each session is **flagged** with the age of the calibration data it ran
under.

**Stale-calibration flag.** Any session executing under calibration older
than 6 hours is marked `stale_calibration: true` with the age in hours. This
is recorded per session and analysed, not absorbed.

**Sensitivity analysis (pre-declared).** The primary Q-A' estimate is
reported (i) across all sessions and (ii) restricted to sessions with fresh
calibration, if both strata contain at least two sessions. If the two differ
materially, that difference is reported as a finding rather than resolved by
choosing a stratum.

**Stale-value guard.** Before each session, any candidate patch containing a
qubit or coupler whose reported error equals exactly 1.0 (IBM's undefined
marker) is **excluded from the candidate pool**, and the exclusion is
recorded. Scoring a patch on a placeholder value would make the archive
policy's selection meaningless for that patch.

### 4. Why this strengthens rather than weakens the study

Q-A' asks whether selection from **passive archived calibration metadata**
beats selection from **direct measurement**. A period in which published
calibration is frozen for days while the device continues to self-adjust is
the condition of **maximum divergence** between those two information
sources: the archive policy reads three-day-old metadata while the probe
measures the device as it currently is.

This is not a degraded operating condition for the experiment. It is the
regime the experiment was designed to discriminate. If the probe policy has
an advantage anywhere, stale-calibration sessions are where it should be
largest — and that is now a testable, pre-declared prediction rather than a
post-hoc rationalisation.

**Pre-declared directional expectation (exploratory):** the P-probe minus
P-archive difference is expected to be more negative (favouring the probe)
in stale-calibration sessions than in fresh ones. Recorded here before any
session-2 data exists. This is an expectation, not an endpoint; the primary
estimand and SESOI are unchanged.

### 5. Unchanged

Everything else in the Stage B commit: the frozen matrix (8 candidates,
256 probe shots, 4096 main shots, 30 main circuits), the three policies,
both logical states reported separately, SESOI 0.010, the pilot-estimation
study class with no confirmatory superiority claim, the frozen decoder and
syndrome table, G5 and G6, the binding cost rule, the 40-minute cap, and all
guardrails. Session 1 (2026-08-07, seed 1001, 39 QPU-seconds, 54/54
circuits) is complete, valid, and unaffected; it is retrospectively flagged
with the calibration age it ran under.

### 6. Deviation entry

**D-B1 (2026-08-09).** The Stage B session gate required a changed published
calibration timestamp. `ibm_fez` did not publish an update for >65 hours
(fleet-wide; `ibm_marrakesh` likewise), exceeding the maximum 60.6-hour gap
observed across 707 archived snapshots and blocking session 2 indefinitely.
The gate is replaced with a 12-hour minimum separation plus per-session
calibration-age flagging and a pre-declared sensitivity analysis. No session
data is affected; session 1 predates the change and is unmodified.
## Amendment A4 (2026-08-14) — backend migration, ibm_fez to ibm_marrakesh
### Pre-declared BEFORE any marrakesh data is collected or examined.

---

### 1. Why

Stage B fixed `ibm_fez` as the study backend. That device has become
effectively unusable for this study.

**Evidence (all recorded before this amendment):**

| observation | value |
|---|---|
| `ibm_fez.status().pending_jobs` (2026-08-14) | **24,668** |
| `ibm_marrakesh.status().pending_jobs` | 0 |
| `ibm_kingston.status().pending_jobs` | 21 |
| probe `d9t3ej1dsedc73aie9e0` (24 PUBs, ~5 s est.) | QUEUED 4 days, never executed |
| minimal test `d9v40ano3ppc73ajptm0` (1 PUB, 1 qubit, 10 shots) | QUEUED 24 h, never executed |
| marrakesh test `d9vnvst0vrcc73bpi050` (identical minimal job) | completed immediately |
| control `d9r7ihopdb6s73e4i4og` (same script, 24 PUBs, ibm_fez) | completed in ~7 min, 2026-08-07 |

Both stalled fez jobs reported `position_in_queue: None` and
`estimated_start_time: None` throughout, while the backend reported
`operational: True, status: active`.

**Ruled out before concluding it was device-side:** job size and PUB count
(a 1-PUB/10-shot job stalled identically); stuck or concurrent jobs (job
list showed no other QUEUED or RUNNING entries); credentials (verified via
`instances()`, and the Scout collector authenticated continuously with the
same token); instance resolution (explicit CRN resolves cleanly); quota
(~39 of 180 promotional minutes remain; queued jobs are not billed).

**Antecedent:** `ibm_fez` and `ibm_marrakesh` both published no calibration
update between 2026-08-06 23:20 and 2026-08-10 10:02 (~83 h, fleet-wide).
The fez backlog is consistent with accumulated global open-plan submissions
during that freeze. A support ticket has been filed.

### 2. The change

**Study backend becomes `ibm_marrakesh`** for all remaining Stage B
sessions.

Justification for marrakesh over kingston, which is also idle and capable:

- Both are 156-qubit Heron devices with `if_else`, `measure`, and `reset`
  in target — the same capability profile G5 verified on fez.
- The QPU Drift Collector has archived **marrakesh since 2026-06-18**: 786
  unique calibration cycles, median gap 1.2 h, most recent 2026-08-14
  11:04, i.e. the device has recovered from the freeze and is cycling
  normally. **`ibm_kingston` has no archive.** P-archive cannot be
  computed without longitudinal history, so kingston would eliminate the
  policy under test.

### 3. What this costs, stated plainly

**Session 1 (fez, 2026-08-07, seed 1001, 39 QPU-seconds, 54/54 circuits)
does not pool with marrakesh sessions.** Cross-session comparison requires
one device. It is retained and reported as a **hardware pilot**
demonstrating that the full apparatus — probe, ranking, three-policy
deploy, interleaving, parsing — executes end to end on real hardware. Its
probe ranking and policy divergence are reported as pilot observations,
never combined with marrakesh data.

The session count restarts at zero on marrakesh. Target remains 4,
minimum 3.

### 4. Gates that must be re-run (all free, all before any session)

Marrakesh is a different physical lattice. Nothing device-specific carries
over.

- **G1 (intervention distinctness)** — re-run on marrakesh cycles. The
  policies may converge on this device even though they disagreed 100% of
  the time on fez. **That outcome is a finding, not a failure**, and
  triggers the section 9 convergence-dominated branch as written.
- **G5 (compile)** — re-run against the marrakesh target: patch
  enumeration, zero-SWAP, conditionals preserved at optimization_level=3,
  layout honoured, no flag-qubit requirement.
- **Stale-value guard (A3)** — re-run; exclude any patch containing a
  qubit or coupler reporting error exactly 1.0.
- **Stage A cost pilot** — re-run on marrakesh. The measured 3 QPU-seconds
  was a fez number. **No cost figure carries across devices**, and Stage B
  sizing is re-derived from the new measurement by the frozen formula.

**G2 (Tier 0 correctness) does NOT need re-running.** It verified the code,
syndrome table, and decoder in ideal simulation; those are device-
independent.

### 5. What does not change

The frozen decoder and syndrome table; the three hardware circuit classes;
duration-matched BARE on all three data qubits; both logical states
reported separately; SESOI 0.010; the pilot-estimation study class with no
confirmatory superiority claim; the staged-commit integrity rules and
forbidden-analyses list; G6 probe validity; the A3 replication unit
(>=12 h separation, calibration-age flagging, stale/fresh sensitivity
analysis); the 40-minute total cap; and every section 10 guardrail.

Prior-work positioning is unchanged. Note that Stein et al.
(arXiv:2601.16123) evaluated repetition codes across IBM Fez, Kingston,
and Pittsburgh, so cross-device work in this setting is established
practice, not a novelty claim.

### 6. Pre-declared, before any marrakesh data exists

The Tier 1 simulation result — that patch selection from passive archived
calibration failed discriminant validity under two independently derived
scoring functions — was obtained on **fez** archive data. Whether it
replicates on marrakesh is **unknown and untested**. It is not assumed
here, and marrakesh G1/G4 outcomes will be reported as their own result,
including if they contradict the fez finding.

### 7. Deviation entry

**D-B2 (2026-08-14).** Study backend migrated from `ibm_fez` to
`ibm_marrakesh` after fez accumulated 24,668 pending jobs and failed to
execute either a 24-PUB or a minimal 1-PUB job over 4 days and 24 hours
respectively, while reporting operational. Migration is platform-driven,
not results-driven: **no marrakesh data had been collected or examined at
the time of this amendment.** Session 1 (fez) is reclassified as a
hardware pilot and excluded from pooled analysis. All device-specific
gates (G1, G5, stale-value guard, Stage A cost pilot) are re-run on the
new backend before any confirmatory session.
## Deviation D-B3 (2026-08-16) — BARE arm was not duration-matched
### Discovered at analysis, before any Q-B result was reported.

---

### 1. What happened

`stage_b.build_main_set` called `tier0.build_bare(state)` without the
`delay_dt` argument, which defaults to **0**. The BARE arm in sessions
11-14 therefore executed as prepare-and-measure — verified from the code
path as depth 2 with zero `delay` instructions — while ENC_PASSIVE and
ENC_ACTIVE ran three full syndrome-extraction rounds (logical depth 31,
transpiled depth 74).

The duration matching required by PREREGISTRATION section 3.3 was never
applied. That requirement exists because the council review of v2
identified an unmatched bare baseline as rigging the comparison:
"comparing a long encoded circuit with an immediately measured bare qubit
would almost guarantee an unfair result."

### 2. Scope of the damage

**Void:** every S = p_BARE / p_L value computed from sessions 11-14.
Those compare an instantaneous measurement against a multi-round circuit
and are biased hard in BARE's favour. They are not reported as
break-even estimates in any form.

**Unaffected:** Q-A' (both arms encoded), E4 (both arms encoded), G6
(probe score vs measured p_L on encoded arms), and the postselection
analysis. None of these involve the BARE arm.

### 3. Remedy

A supplementary duration-matched run was executed on 2026-08-16
(job `da0rpbqein7c73bclnt0`, 37 QPU-seconds, ibm_marrakesh).

**Deriving the match.** Qiskit cannot schedule circuits containing
control flow — `TranspilerError: "Some options cannot be used with
control flow. Got scheduling_method='alap', but the entire scheduling
stage is not supported."` — and the transpiled ENC_ACTIVE exposes no
duration. ENC_PASSIVE was scheduled instead: identical encoding, three
rounds of CZ/measure/reset, identical final readout, everything except
conditional-branch execution.

Matched delays obtained per patch: 5272, 5284, 5281 dt (dt = 4 ns), i.e.
~21.1 µs. **Independently cross-checked by hand** from target instruction
durations (cz 17 dt, measure 671 dt, reset 680 dt, sx 9 dt), giving
~5109 dt for the same sequence — within 3.1% of the scheduler, so the
figure is not an artifact of the pass.

**Residual mismatch, stated rather than hidden.** ENC_PASSIVE is
*exactly* matched to the BARE delay. ENC_ACTIVE is *under*-matched by the
feedforward-branch time, which is precisely the quantity that cannot be
scheduled. BARE therefore receives slightly less decoherence exposure
than ENC_ACTIVE, which biases **against** the encoded arm — it makes
"encoding helps" harder to claim, not easier.

A guard now raises rather than submitting if the delay fails to land, so
an unmatched BARE cannot be executed silently a second time.

### 4. Corrected Q-B result (single window)

All three patches, both encoded arms, 4096 shots per cell.

**|1_L⟩ — encoding helps, 6 of 6 cells**

| patch | BARE mean | ENC_PASSIVE | S | ENC_ACTIVE | S |
|---|---|---|---|---|---|
| (1,2,3,4,5) | 0.1339 | 0.0798 | 1.68 | 0.0615 | 2.18 |
| (2,3,4,5,6) | 0.1536 | 0.0835 | 1.84 | 0.0654 | 2.35 |
| (10,11,12,13,14) | 0.1199 | 0.0637 | 1.88 | 0.0491 | 2.44 |

**|0_L⟩ — overhead dominates, 6 of 6 cells**

| patch | BARE mean | ENC_PASSIVE | S | ENC_ACTIVE | S |
|---|---|---|---|---|---|
| (1,2,3,4,5) | 0.0045 | 0.0188 | 0.24 | 0.0215 | 0.21 |
| (2,3,4,5,6) | 0.0024 | 0.0308 | 0.08 | 0.0251 | 0.09 |
| (10,11,12,13,14) | 0.0034 | 0.0183 | 0.19 | 0.0212 | 0.16 |

**Baseline choice materially affects the |1_L⟩ magnitude.** The tables
above use the arithmetic mean of the three data qubits. Section 3.3
designates the *score-designated best constituent* as primary. Bare |1_L⟩
error varies 2-3x across the three data qubits within a patch (e.g.
0.0886, 0.1289, 0.1841), so the baseline matters. Against the best
*measured* bare — labelled post-outcome descriptive only, per section 3.3
— S falls to **1.11-1.33 (ENC_PASSIVE)** and **1.44-1.69 (ENC_ACTIVE)**.
Still above 1, substantially less dramatic. Both are reported.

### 5. Interpretation, bounded

The distance-3 bit-flip repetition code, run as a three-round memory on
ibm_marrakesh, **suppresses logical bit-value error for |1_L⟩ relative to
a duration-matched physical qubit**, by a factor between roughly 1.1 and
2.4 depending on the baseline convention, and **fails to do so for
|0_L⟩**, where overhead exceeds any benefit by roughly 4-13x.

The mechanism is consistent with the device physics and was not assumed
in advance: over ~21 µs of matched idle, a bare |1⟩ relaxes toward |0⟩
(measured bare |1_L⟩ error 0.077-0.235), and those relaxation events are
exactly the X-channel bit flips this code corrects. A bare |0⟩ sits in
the ground state and barely decays (measured 0.0005-0.0095), leaving
nothing to protect and only overhead to pay.

This is why section 3.4 requires both logical states to be reported
separately before any averaging. Averaging them here would produce a
number describing neither regime.

**Claim boundary, unchanged:** this is suppression of logical *bit-value*
error in a computational-basis memory. It is not a claim about a
generally protected logical qubit, and no phase-coherence claim is made
or implied.

**Limitations:** single window; no cross-session replication; not paired
by session; executed under a calibration cycle frozen since 2026-08-14
11:04. The suppression figures are a point estimate from one job, not a
replicated effect.
## Amendment A5 (2026-08-16) — declared additions to complete QEC-P1
### Pre-declared BEFORE any of these runs. Purpose stated for each.

---

### 0. Why additions at all

The pre-declared analysis returned three underpowered or unattributable
results. These additions strengthen **existing** gates and questions.
They are not a search for new significant effects in collected data.

Each addition below states, before execution, what it measures and what
outcome would count against the study's own findings.

**Budget:** ~35 of 40 QPU-minutes remain (5 spent). Every addition here
fits inside 5 minutes even at 3x the measured cost. The 40-minute cap is
unchanged.

**Q-A' is NOT extended, deliberately.** Its session-to-session sd is
0.067 against SESOI 0.010; detecting that effect would need on the order
of 350 sessions. More importantly the variance is structural, not
statistical: each session compares a *different pair of patches*, so
"policy" is confounded with "which patch was selected." Additional
sessions cannot resolve that. Q-A' stands as reported: a null with
variance exceeding any plausible effect, n=3 discordant.

---

### 1. G6-extended — probe validity, properly powered

**Problem.** G6 currently rests on 7 points pooled across sessions, rho =
+0.414, sitting exactly on the declared 0.4 threshold. n=7 gives a
standard error near 0.41, so the interval spans almost the whole range.
The pooling also confounds patch quality with session-to-session device
state. And session 11 contains direct counter-evidence: two patches with
*identical* probe scores (0.12109) measured p_L of 0.1289 and 0.0430, a
3x difference.

**Addition.** Deploy **all 8 probed candidates** — not only the 2-3
selected — with ENC_ACTIVE, |1_L>, 4096 shots, in the same job as the
probe. This yields 8 **within-session** (probe score, measured p_L) pairs
per window, blocked by session, with no cross-session confound.

**Analysis (frozen now).** Spearman rho between probe score and measured
p_L, computed **within each session** and reported per session, then
combined across sessions. Thresholds unchanged: >=0.4 valid, 0.2-0.4
weak, <0.2 fail.

**What would count against the study.** If within-session rho is near
zero, the probe does not predict logical error, probe-based selection has
no discriminant validity on this device at 256 probe shots, and Q-A' and
Q-C both lose their premise. That outcome is reportable and will be
reported.

**Sessions:** 2 minimum, 3 preferred. ~27 s each.

---

### 2. Q-B replication

**Problem.** The corrected Q-B result (D-B3) is a **single window**. The
|1_L> vs |0_L> asymmetry is the study's most interesting physical finding
and currently has no replication.

**Addition.** Repeat the duration-matched supplement in 2 further windows
separated by >=12 h, identical protocol, same three patches.

**Analysis (frozen now).** S reported per window per state per arm; the
|1_L> and |0_L> strata never averaged together. The claim is a
replicated effect only if the direction holds in all windows.

**What would count against the study.** If S for |1_L> falls below 1 in a
later window, the single-window result was not robust and will be
reported as such.

**Cost:** ~37 s per window (measured).

---

### 3. DUMMY_FF in-session — E4 attribution

**Problem.** E4 found ENC_ACTIVE beating offline-decoded ENC_PASSIVE in
12 of 12 cells. The design attributes that to in-circuit correction
preventing error accumulation across rounds — but DUMMY_FF, the
diagnostic that isolates control-path and latency cost, ran only in Stage
A and never alongside the E4 comparison. E4 therefore describes an effect
it cannot attribute.

**Addition.** Include DUMMY_FF (same measure-and-conditional path, a
conditional X on an already-measured-and-reset ancilla) on each deployed
patch, |1_L>, in the same job as ENC_ACTIVE and ENC_PASSIVE.

**Analysis (frozen now).** p_L(DUMMY_FF) minus p_L(ENC_PASSIVE) estimates
the cost of traversing the conditional-control path with no corrective
action. If that difference is small while ENC_ACTIVE beats ENC_PASSIVE
substantially, the E4 benefit is attributable to correction rather than
to any artifact of the dynamic-circuit path.

**Validity condition, unchanged from section 3.3:** DUMMY_FF is used only
if the transpiled circuit provably retains the conditional blocks. It
carried 9/9 through optimization_level=3 at G5. If a future transpile
drops them, the diagnostic is dropped and E4 remains unattributed.

**Cost:** ~12 s.

---

### 4. Q-D (NEW QUESTION) — break-even versus syndrome-round count

**This is a new question, declared here before any data exists.** It is
not a re-analysis of collected data.

**Motivation.** The Q-B result showed encoding helps |1_L> (S 1.1-2.4)
and fails |0_L> (S 0.08-0.24) at three syndrome rounds. The proposed
mechanism is that over ~21 µs of matched idle a bare |1> relaxes toward
|0>, producing exactly the X-channel bit flips this code corrects, while
a bare |0> sits in the ground state and offers nothing to correct.

If that mechanism is right, the effect should be **dose-dependent in
exposure time**.

**Addition.** Repeat the duration-matched Q-B protocol at **1, 3, and 5
syndrome rounds**, on one patch, both logical states. BARE delay is
re-derived per round count from the ENC_PASSIVE schedule at that count.

**Pre-declared expectation.** The **state asymmetry** — S(|1_L>) minus
S(|0_L>) — should **increase** with round count, because longer exposure
produces more relaxation for the code to correct while |0_L> gains
nothing. No directional prediction is made for S itself in either state
alone: correction opportunities and accumulated measurement/reset
overhead both grow with rounds, and their balance is not predictable in
advance from what is known here.

**What would count against the mechanism.** If the state asymmetry is
flat or shrinks with round count, the relaxation explanation for the
Q-B result is not supported, and the |1_L> advantage requires a different
account.

**Cost:** 3 round-counts x 5 circuits x 2 states x 4096 shots, ~2 min.

---

### 5. Unchanged

SESOI 0.010; pilot-estimation study class with no confirmatory
superiority claim; frozen decoder and syndrome table; the claim boundary
(logical bit-value error, computational basis, this code, this device —
never a generally protected logical qubit, never a phase claim); both
logical states reported separately before any averaging; postselection
reporting rules; A3 replication unit and calibration-age flagging; A4
backend and re-run requirements; the 40-minute cap; all guardrails.

The Tier 1 negative, Q-A' null, and the D-B3 deviation stand as reported
and are not revisited by anything in this amendment.
