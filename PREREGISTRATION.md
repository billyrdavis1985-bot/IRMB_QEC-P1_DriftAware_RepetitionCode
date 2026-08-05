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
