# QEC-P1 · Section 4.3 Multiverse Preregistration

STATUS: READY TO FREEZE. Freeze = commit + tag `multiverse-prereg`, done before
window 2 is submitted. No confirmatory data exists at freeze time.

Frozen spec: this document, `multiverse.py`, `mv_run.py`, `multiverse_loader.py`,
`frozen_decode.py`, `qec/g6_extended.py` (with candidate pinning) and
`qec/mv_preflight.py`.

## Question and the decision it buys

Does a patch's d=3 repetition-code logical-error ranking on IBM Heron
(ibm_marrakesh) hold from one measurement window to the next, about a day later?
"Effect present" = the ranking is NOT preserved (instability).

- Robust: the drift mechanism from QEC-P1 Section 4.3 ("patch ranking reorders
  faster than a measure-then-act cycle") becomes a preregistered finding that
  QEC-P5 (syndrome-as-sensor) can be motivated on.
- Fragile or not supported: QEC-P1's claim narrows and QEC-P5 needs an
  independent motivation. Reported either way.

## Data

- Patches: the 8 window-1 candidates, pinned from `runs/g6ext_1_result.json`
  (2-3-4-5-6, 3-4-5-6-7, 1-2-3-4-5, 16-3-4-5-6, 10-11-12-13-14,
  53-54-55-59-75, 9-10-11-12-13, 8-9-10-11-12). Every new window deploys exactly
  these, in this order, enforced by `--pin-from`.
- Circuit: ENC_ACTIVE, |1_L>, 3 rounds, 4,096 shots per patch (same as window 1).
- Decode: the frozen QEC-P1 decoder via `qec.analyze.enc_pL`. Tripwire: window 1
  must reproduce the published G6 values 10-11-12-13-14 = 0.0559 and
  53-54-55-59-75 = 0.1265, or the run stops.

## Comparisons

- PRIMARY: window 2 vs window 3. Two fresh windows at least 24 hours apart,
  each under a different published calibration cycle (checked by
  `mv_preflight`). This is the day-scale test.
- SECONDARY: window 1 (2026-08-16) vs window 2. About two months apart and
  window 1 ran under a frozen calibration cycle, so instability is expected
  here for reasons beyond the mechanism. Reported, never used for the verdict.

## Statistics and thresholds

- spearman: unstable if < 0.40 (the study's own G6/A5 threshold)
- kendall (tau-a): unstable if < 0.40
- swap_fraction (share of patch pairs whose order flips): unstable if >= 0.25

Each computed as a point estimate and as the median over 2,000 binomial
bootstrap redraws of both windows (per-cell shot counts).

## World set: 54 worlds

3 statistics x 2 noise treatments x 9 patch sets
(all 8, plus 8 leave-one-out sets of 7).

Leave-one-out replaces the earlier "drop overlapping patches" fork. Any overlap
rule fails on this patch set: seven of the eight patches sit in one contiguous
qubit region (0 to 16) and chain into each other, so a "shares 3+ qubits" rule
drops 7 of 8 and leaves nothing to rank. Leave-one-out answers the question the
fork was meant to ask: does the result depend on any single patch?

Survival = fraction of the 54 worlds flagging instability.

## Interpretation bands

- ROBUST: survival >= 0.85 and both controls pass
- FRAGILE: 0.40 <= survival < 0.85
- NOT SUPPORTED: survival < 0.40

What "unstable" means here: reshuffling at least as large as a +/-0.015
rank-reversing shift. On the window-1 patches the neighbour-to-neighbour gap is
about 0.004 but the full spread is about 0.07, so a 0.010 shift leaves Spearman
at +0.548 even with zero shot noise. Smaller reshuffles read as stable by
definition, not for lack of power. Raising shots to 16,384 did not change this
(detection at 0.010 was 0.43 at 16,384 vs 0.52 at 4,096, within draw noise).

## Controls (validated before freezing; `python3 multiverse.py --selftest`)

Negative control: both windows redrawn from the window-1 rates with fresh
shot noise, no drift. 300 draws.
- binomial noise: 0.006
- widened to the worst repeat spread measured in Q-E (SD ratio 1.42): 0.047
- Pass: <= 0.10 in both. PASS.

Positive control: graded rank-reversing drift (better half pushed up, worse
half down by delta, then redrawn with shot noise). At delta = 0 it equals the
placebo, so it cannot pass by construction. 60 draws per point.

| delta | 0.000 | 0.005 | 0.010 | 0.015 | 0.020 |
|---|---|---|---|---|---|
| survival | 0.002 | 0.116 | 0.435 | 0.940 | 0.996 |

Pass: >= 0.90 at delta = 0.015. PASS (0.940).

Pipeline check (synthetic files in the real g6ext schema, through
`mv_run.py`): identical windows -> 0.000; full best-to-worst reversal -> 1.000.

## Pre-freeze design decisions (logged; not amendments, nothing was frozen)

D1. Removed `mean_abs_delta`. Under the placebo its bootstrap variant flagged
instability in about 90% of no-drift draws (bootstrapping a magnitude compounds
both windows' noise), and it measures magnitude while the claim is about ranking.

D2. Replaced the positive control. The v1 control (random permutation plus a
shift) scored about 0.95 at zero injected drift: it detected its own
permutation, so it could not fail. Replaced by the graded design above.

D3. Replaced the overlap-subset fork with leave-one-out (reason above).

D4. Moved the positive-control gate from 0.010 to 0.015, the smallest planted
shift that crosses the instability threshold with zero shot noise.

D5. Changed the primary comparison to two fresh windows (W2 vs W3) instead of
W1 vs a new window, because window 1 is two months old and ran under a frozen
calibration cycle.

## Run protocol

Before each window: `python -m qec.mv_preflight`. Submit only on GO. If a
pinned patch reports error >= 1.0 or a missing coupler, stop and log it; do not
drop or swap the patch without a logged amendment.

## Limitations (pre-stated)

- One primary day-pair x 8 patches: the survival fraction is "across defensible
  analyses of this comparison," not "across many day-pairs."
- |1_L> only.
- Seven of eight patches share qubits, so they are not independent samples of
  the device.
- The calibration-boundary, timestamp-ordering and autocorrelation forks need
  more than two windows and are not run here.

## Report rule

Report the primary survival fraction and band whatever it is, including NOT
SUPPORTED. No world is added or removed after the freeze without a logged
amendment. Window 1 is committed as input; no survival number is written until
windows 2 and 3 exist.

## Amendment MV-A1 (2026-10-19, after window 2, before any window-3 data)

What happened. Window 3 was submitted at 2026-10-19 19:12 ET after the
preflight printed GO. The backend was in fact in maintenance
(status 'maintenance', operational flag True, 1,356 pending jobs), and three
pinned patches (10-11-12-13-14, 9-10-11-12-13, 8-9-10-11-12) showed a maximum
qubit readout error of 0.434, against 0.032-0.034 in windows 1 and 2. Both jobs
(dbba7s424mrc73bogtug, dbba7sc24mrc73bogu00) were cancelled while QUEUED. No
window-3 data was returned or viewed.

Why GO was wrong. The frozen preflight checked only the operational flag, not
the status message, and flagged only errors >= 1.0. A 43% readout error passed
as "ok". Running then would have measured a maintenance-period device with one
failing qubit shared by three patches. A rank change from that is a hardware
fault, not the drift the study tests.

Changes (code: qec/mv_preflight.py).
1. STOP unless backend status is 'active'.
2. DEGRADED patch = any qubit readout error > 0.10 or any two-qubit error
   > 0.05 (window 1/2 maxima: 0.034 / 0.004). DEGRADED is a STOP.
3. On a DEGRADED STOP, wait for a later published calibration cycle and rerun
   the preflight. If any pinned patch is still DEGRADED 7 days after
   2026-10-19, submit window 3 anyway, and report the primary result twice: as
   preregistered (all 54 worlds), and as a labeled sensitivity analysis with the
   DEGRADED patches removed. The preregistered number stays primary.
4. The 24-hour minimum separation from window 2 is unchanged; window 3 may be
   later than that.

Analysis, thresholds, world set and bands are unchanged.
