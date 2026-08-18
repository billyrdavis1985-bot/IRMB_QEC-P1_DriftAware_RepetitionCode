# Drift-Aware Patch Selection Fails Where the Target Moves Faster Than the Measurement

**A preregistered pilot study of distance-3 repetition-code memory on IBM Heron hardware**

Billy R. Davis Jr. — Hudson Forge Technologies, IRMB program
Independent research, self-funded

**Status: DRAFT.** Q-D (round-count sweep) is queued at the time of
writing; section 4.5 is a placeholder. All other results are final.

---

## Abstract

*(to be written last — draft the sections first, then compress)*

Placeholder claim set, in the order the evidence supports it:

1. Five independent instruments failed to predict distance-3
   repetition-code logical error on `ibm_marrakesh`: a calibration-archive
   composite under two independently derived weightings, a 256-shot
   measured probe, a 4096-shot data-qubit-only probe, and an
   archived-feature diagnosis.
2. A stability test offers a mechanism: absolute logical error moves ~31%
   over ten minutes and 25-31% between windows, and patch *rankings*
   reorder on that timescale, while within-job behaviour is binomially
   stable.
3. The code does suppress logical bit-value error for |1_L> against a
   duration-matched physical qubit (S ~ 1.5-2.4) and fails to for |0_L>
   (S ~ 0.08-0.48), replicated across two windows.
4. Active in-circuit correction outperforms offline decoding of the same
   syndrome records, confirmed at 20,480 shots per arm, and the advantage
   is attributable to correction rather than to the conditional-control
   path.
5. Within-job ratios are ~3x more stable than absolute rates, which
   validates paired designs and explains why comparisons *within* a job
   survive while selection *between* time-separated measurements does not.

Total quantum resource: **438 QPU-seconds** across 26 jobs.

---

## 1. Introduction

*(to draft)*

Framing to hit:
- Drift is real and documented; calibration-aware qubit selection has a
  literature (Tannu & Qureshi ASPLOS 2019; Murali et al. ASPLOS 2019).
- Recent work reports large gains from *measured probe* selection for QEC
  (Ashuraliyev, DAQEC-Benchmark; and the noise-level moderation preprint).
- This study asked the narrower question a self-funded researcher can
  answer: does a longitudinal calibration archive, or a short measured
  probe, predict logical error well enough to drive patch selection at
  d=3 on a 156-qubit Heron device?
- The answer is no, five times over, and the mechanism is measurable.
- **What this is not:** not a fault-tolerance claim, not a phase-coherence
  claim, not a contradiction of the probe-selection literature — a
  boundary condition on it.

## 2. Methods

### 2.1 Preregistration and amendments
Staged preregistration with a Stage A engineering pilot and a Stage B
confirmatory commit, plus eight amendments (A1-A8) and four logged
deviations (D-A1, D-A2, D-B1/2/3). Every design change is timestamped
before the run it governs. See `PREREGISTRATION.md`.

### 2.2 Code and circuits
Distance-3 bit-flip repetition code, 3 data + 2 ancilla qubits, frozen
syndrome-to-correction table, three hardware circuit classes:
duration-matched BARE, ENC_PASSIVE (syndromes recorded, decoded offline),
ENC_ACTIVE (in-circuit `if_else` feedforward). Both logical states
reported separately throughout.

### 2.3 Instrument
QPU Drift Collector: Raspberry Pi 5 polling IBM calibration hourly since
2026-06-18. 707 unique `ibm_fez` cycles and 786 `ibm_marrakesh` cycles at
time of writing, median inter-cycle gap 1.2 h.

### 2.4 Selection policies
- **P-archive** — rolling frozen score over all prior cycles.
- **P-today** / **P-probe** — most recent cycle, or short measured probe.
- **P-generic** — transpiler default.

### 2.5 Gates
G1 intervention distinctness; G2 decoder correctness (exhaustive at 1, 3
and 5 rounds); G5 compile verification on the live target (zero SWAP,
conditionals preserved); G6 probe validity. G3/G4 retired for Q-A' per A2.

### 2.6 Backend migration
`ibm_fez` to `ibm_marrakesh` (A4), platform-driven, declared before any
marrakesh data existed. See `runs/README.md`.

## 3. Simulation (Tier 1)

*(to draft — the negative and its diagnosis)*

Held-out evaluation, process-isolated after an Aer crash rate of ~8.7%.
Archive policy consistently worse out of sample under both weightings.
Discriminant-validity diagnosis over 131 cells: readout dominates
(rho +0.83 to +0.91 per cell), temporal variance and tail penalties
**anti**-predictive (-0.114, -0.188). Re-weighting from measured
correlations did not rescue it — G4 got worse, 48% to 41%.

## 4. Hardware results

### 4.1 Q-A' — policy comparison
Three discordant sessions of four. Paired mean delta **+0.00073**, sd
**0.0673**. Reported as a null with variance far exceeding any plausible
effect. Not extended: the variance is structural, since each session
compares a different pair of patches.

### 4.2 G6 and probe v2 — probe validity
All 8 candidates probed and deployed within one window. rho **-0.072** at
256 shots; **-0.335** at 4096 shots with data-qubit-only aggregation.
Pre-declared failure condition; fired both times.

### 4.3 Q-E — temporal stability
Within-job binomially stable (3 of 4 cells, chi-square p 0.12-0.73).
Across ten minutes, `(1,2,3,4,5)` moved 0.0913 to 0.0631 with
non-overlapping intervals. Ranking of two patches collapsed from a 1.7x
ratio to a tie.

### 4.4 Q-B — break-even, duration-matched
Two windows, 12/12 cells replicate by direction. |1_L> S 1.49-1.88
(passive) and 1.74-2.44 (active); |0_L> S 0.08-0.48. Baseline convention
matters: against the best measured constituent qubit rather than the
mean, |1_L> S falls to 1.11-1.69. Both reported.

### 4.5 Q-D — break-even versus round count
**PLACEHOLDER — job `da2ct4rotlns7398cc30` queued.**
Exposure 9.57 / 21.09 / 32.61 us at 1 / 3 / 5 rounds. Pre-declared
expectation: the state asymmetry S(|1_L>) - S(|0_L>) increases with round
count if relaxation drives the Q-B result. No prediction made for S alone.

### 4.6 E4 — feedforward
Sessions 11-14: 12/12 negative, mean -0.024. An underpowered 4096-shot
re-test gave -0.0055 and one sign reversal. Powered re-test at 20,480
shots/arm: **-0.0073, -0.0299, -0.0132, all intervals excluding zero**.
Attribution: correction benefit excludes zero in all three; control-path
cost includes zero in two of three.

## 5. Discussion

*(to draft)*

- The five failures are one failure with one cause.
- Selection compares measurements separated in time; the paired
  within-job comparisons that survived are exactly those that are not.
- Boundary condition on published probe-selection results, not a
  contradiction: different code distance, device, patch size and decoder.
- What would change the answer: measurement from *inside* the running
  computation, which is the QEC-P5 direction.

## 6. Limitations

- Pilot estimation class; no confirmatory superiority claim anywhere.
- Q-A' rests on three discordant sessions.
- All marrakesh sessions ran under one frozen calibration cycle; the A3
  fresh-versus-stale sensitivity analysis is **not evaluable**.
- Q-E tests stability of two patches, not of the ranking across eight,
  which is what selection actually depends on.
- Single device for the reported results; the fez pilot is not pooled.
- ENC_ACTIVE is under-matched against BARE by the unschedulable
  feedforward-branch time, which biases *against* the encoded arm.
- Every suppression figure is logical bit-value error in a
  computational-basis memory. No phase claim.

## 7. Related work

Stein et al. arXiv:2601.16123 (calibration-conditioned FiLM decoders,
IBM repetition codes, >2.7M shots); Bhardwaj, Takou, Lin & Brown
arXiv:2511.09491 (sliding-window drift estimation from syndromes);
Ashuraliyev, DAQEC-Benchmark (Zenodo 10.5281/zenodo.18045662) and the
noise-level moderation preprint (Research Square rs-8475008); Tannu &
Qureshi ASPLOS 2019; Murali et al. ASPLOS 2019; Wootton
arXiv:2207.00553.

No novelty is claimed over any of these. **Source caveats:** rs-8475008 is
an unrefereed preprint, single-author, with a self-admittedly post-hoc
threshold and internally inconsistent reported Ns.

## 8. Reproducibility

MIT-licensed. All 26 job IDs, devices, dates and roles in
`runs/README.md`, including the three superseded artifacts. Preregistration
and all amendments in `PREREGISTRATION.md`. Simulation reproduces without
an IBM account.

## 9. Acknowledgements and honest notes

Errors found and corrected during the study, all logged: a DataBin
register-name collision that made an injected-X check read 0.9043 instead
of 0.1582 (D-A1); a budget arithmetic error in a sizing script (D-A2); a
BARE arm that was never duration-matched, voiding the first Q-B result
(D-B3); a G5 run compiled against the wrong backend; and an underpowered
attribution test whose null was mistaken for a reversal until it was
powered properly.
