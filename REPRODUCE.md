# Reproducing QEC-P1

Everything except the hardware execution reproduces without an IBM
account. The hardware results can be re-analysed from the committed
counts without spending any quantum time.

Total original cost: **475 QPU-seconds across 26 jobs**.

---

## What runs without an IBM account

| step | command | what it checks |
|---|---|---|
| Decoder correctness (G2) | `python -m qec.tier0 --verify` | all 64 three-round syndrome histories decode deterministically; single-X errors correct on every data qubit; ideal logical error is zero |
| Probe module | `python -m qec.probe --verify` | probes read zero on a noiseless simulator, track graded injected noise monotonically, and the validity gate passes a perfect ranking while failing a scrambled one |
| Policy distinctness (G1) | `python -m qec.layouts "data/snapshots_marrakesh/*_converted.json"` | how often the two selection policies choose different patches, and by what score margin |
| Tier 1 simulation | `python -m qec.tier1_runner --snapshots "data/snapshots_marrakesh/*_converted.json" --holdout 8 --shots 4000` | the held-out policy comparison. **Expect crashes** — see below |
| Score diagnosis | `python -m qec.diagnose_score --snapshots "data/snapshots_marrakesh/*_converted.json"` | which scoring features actually correlate with simulated logical error |
| Figures | `python make_figures.py` | regenerates all four figures from the committed run data |

### Setup

```
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
pip install qiskit qiskit-aer matplotlib
```

`qiskit-ibm-runtime` is needed only for the hardware and compile steps.

### Expect Aer to crash during Tier 1

Aer crashes non-deterministically on this workload (exit `-1073741819` on
Windows, SIGSEGV on Linux). This is not a bug in this code and it is not
fixable from Python — it reproduces on both platforms, on physically
valid calibration values, with and without dynamic circuits, and a reused
simulator crashes on its second run where the same condition passes when
run first in a fresh process.

`qec/tier1_runner.py` therefore executes each condition in its own
subprocess. Crashed cells are recorded with exit codes and excluded from
analysis. **Observed crash rates were 8.8% and 8.6%.** Results append to
`runs/tier1_partial.jsonl` as they land, so an interrupted run keeps
everything it earned; `--resume` skips cells already on disk.

A crash rate in that range is expected. A rate near zero or near 100%
suggests a different environment and is worth reporting.

---

## Section 3 (Tier 1 simulation) — where the evidence lives

The Tier 1 sweeps reported in Section 3 were executed in Google Colab,
after Aer was found to crash on the local Windows environment. **The JSON
outputs those runs produced were never retrieved from that session before
it expired and are not in this repository.**

What is preserved:

| artifact | what it holds |
|---|---|
| `notebooks/IRMB_QEC_P1.ipynb` | the complete console output of both sweeps — all 432 conditions each, both gate evaluations, and the full feature-correlation table |
| `runs/tier1_from_notebook.csv` | those per-cell results parsed into a table by `extract_tier1.py` |

Re-derive the table yourself with:

    python extract_tier1.py

The script prints recomputed policy deltas alongside the published ones.
They agree to rounding; two of twelve differ in the fourth decimal,
because the console log carries p_L to four places while the original JSON
held the underlying counts.

**Consequence:** Section 3's per-cell values are auditable and its
aggregate statistics are preserved verbatim in the notebook, but its raw
count data is not in this repository. Confidence intervals cannot be
recomputed from the CSV, only point values.

Re-running Tier 1 from scratch is possible — `qec/tier1_runner.py` is
committed — but requires the calibration archive, which is gitignored for
size. The Aer crash is non-deterministic, so a fresh run will fail on a
different subset of cells.

## What needs an IBM account but no quantum time

| step | command |
|---|---|
| Compile gate (G5) | `python -m qec.g5_compile --patches auto --top 12 --snapshots "data/snapshots_marrakesh/*_converted.json"` |
| Stale-value guard | `python check_stale.py` |
| Post-maintenance comparison | `python check_postmaint.py` |

These read backend targets and calibration metadata and transpile
locally. They submit nothing.

**G5 must pass before any hardware run**: zero SWAP insertion, all nine
conditional blocks preserved at optimization level 3, layout honoured,
and every data-ancilla coupler present so no flag qubits are required.

---

## Re-analysing the hardware results at zero cost

All counts are committed. Re-analysis touches no hardware.

```
python -m qec.analyze --sessions 11 12 13 14
python -m qec.g6_extended --retrieve runs/g6ext_1_jobs.json
python -m qec.probe_v2   --retrieve runs/probev2_1_jobs.json
python -m qec.stability  --retrieve runs/stability_jobs.json
python -m qec.rounds_sweep --retrieve runs/qd_jobs.json
python -m qec.e4_powered --retrieve runs/e4pow_1_jobs.json
python qb_report.py       # Q-B window 1
python qb_report_2.py     # Q-B window 2
```

`--retrieve` fetches results IBM already holds for a completed job. It
costs nothing and can be re-run freely. It is also how three errors in
this study were corrected without respending any quantum time.

**Read `runs/README.md` before interpreting any of it.** It maps every
job to its device, date and role, and marks three superseded artifacts.
In particular the BARE cells in `session_11-14_counts.json` are void —
the arm ran without its duration-matching delay (deviation D-B3) — and
the Q-B supplements replace them.

---

## Re-running on hardware

Only if you have quantum time and want fresh data. Every submission
script has `--dry-run` (full pipeline locally, no account contact) and
`--retrieve`, and writes job identifiers to disk **before** waiting, so an
interrupt never orphans a job.

```
python -m qec.stage_a      --dry-run           # engineering pilot
python -m qec.stage_b      --dry-run --session 11
python -m qec.qb_supplement --dry-run          # duration-matched break-even
python -m qec.g6_extended  --dry-run           # probe validity, 8 candidates
python -m qec.probe_v2     --dry-run           # probe redesign
python -m qec.stability    --dry-run           # temporal stability
python -m qec.rounds_sweep --dry-run           # exposure sweep
python -m qec.e4_powered   --dry-run           # powered feedforward test
```

Replace `--dry-run` with `--submit` to execute. Each prompts for typed
confirmation first.

### Costs actually measured

| run | circuits | shots | QPU seconds |
|---|---|---|---|
| Stage A pilot | 7 | 512 | 3 |
| Session (probe + main) | 24 + 30 | 256 / 4096 | 40 |
| Q-B supplement | 30 | 4096 | 37 |
| G6-extended | 32 | 256 / 4096 | 15 |
| Probe v2 | 32 | 4096 | 39 |
| Stability (two jobs) | 24 | 4096 | 32 |
| Rounds sweep | 30 | 4096 | 37 |
| Powered E4 | 45 | 4096 | 54 |

Queue time is unrelated to these figures and unpredictable. During this
study a four-second job waited roughly eight days on a backlogged device.

### The backend is not interchangeable

Scripts target `ibm_marrakesh`. Cross-session comparison requires one
device; the `ibm_fez` pilot is retained but never pooled. Changing the
backend requires re-running G1, G5, the stale-value guard, and the Stage A
cost pilot — no cost figure carries across devices.

---

## Collecting your own archive

`qpu-drift-collector` runs on a Raspberry Pi 5, polling IBM's calibration
API hourly and deduplicating on calibration timestamp so each stored file
is a distinct cycle. Convert raw snapshots to the study schema with:

```
python3 convert_snapshots.py --backend ibm_marrakesh --out ~/converted
```

The converter carries `calibration_ts` forward, which matters: an earlier
version stored only the pull time, so deduplication was by poll rather
than by cycle. On this device the two coincide (median gap 1.2 hours,
hourly polling), but that is a property of the device, not of the method.

---

## If your numbers differ

Expected. The study's own finding is that logical error moves ~31% over
ten minutes and 25-31% between windows on the same patch. Absolute rates
will not reproduce.

What should reproduce:

- **Directions.** Encoding helps the excited state and not the ground
  state; the state asymmetry grows with exposure; in-circuit correction
  beats offline decoding of the same records.
- **The ratio being more stable than either arm.** Within-job pairing
  cancels most of the drift.
- **Selection failing to predict.** If a probe or archive score predicts
  logical error on your device, that is a genuinely interesting result and
  worth reporting — it would bound where this study's negative applies.
