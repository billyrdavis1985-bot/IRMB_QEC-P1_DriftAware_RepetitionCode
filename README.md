# QEC-P1 — Drift-Aware Repetition-Code Break-Even Study

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22050537.svg)](https://doi.org/10.5281/zenodo.22050537)

**Can calibration data tell you where to put an error-correcting code?**

Five instruments were tried on a 156-qubit IBM Heron processor. None
predicted the logical error rate of a distance-3 bit-flip repetition
code. A stability measurement explains why — and the same measurement
explains what *did* work.

**Total quantum resource: 438 QPU-seconds across 26 jobs.**

📄 **[Full write-up: PAPER.md](PAPER.md)** ·
🔬 **[Preregistration and all amendments](PREREGISTRATION.md)** ·
🧾 **[Evidence provenance: every job ID and role](runs/README.md)** ·
🔁 **[Reproduce it](REPRODUCE.md)**

---

## The result in one figure

![Stability within a job against the ten-minute change](figures/fig2_stability.png)

Two patches, six interleaved repeats per job. Within a job, logical error
is binomially stable. Ten minutes earlier — the diamonds at left — those
same two patches differed by a factor of 1.7. By the time the job ran,
they were indistinguishable.

Selection compares a measurement taken at one moment against performance
at another. That interval is where the information is lost.

---

## What was found

### Five instruments, no prediction

| instrument | result |
|---|---|
| Calibration-archive score, original weights | failed discriminant validity |
| Same score, weights fitted to measured correlations | failed again, slightly worse |
| Measured probe, 256 shots | Spearman **ρ = −0.072** |
| Measured probe, 4096 shots, corrected aggregation | Spearman **ρ = −0.335** |
| Raw published calibration across a known device change | explains ~17% of a five-fold regression, and predicts the bare arm backwards |

A sixteen-fold improvement in probe precision did not help. The failure is
structural, not a matter of instrument design.

### Why: the target moves faster than the measurement

Logical error is stable *within* a job (binomially consistent across six
interleaved repeats) and moves roughly **31% across ten minutes**, with
patch rankings collapsing over the same interval.

### What did work — everything measured inside one job

- **Break-even is state-dependent.** Against a duration-matched physical
  qubit, the code suppresses logical bit-value error for |1⟩ (S = 1.5 to
  2.4) and fails to for |0⟩ (S = 0.08 to 0.48). All twelve cells replicate
  by direction across two windows 33 hours apart.
- **The asymmetry is dose-dependent.** Across exposures of 9.6, 21.1 and
  32.6 µs it rises monotonically (Spearman +1.00) — bare |1⟩ error grows
  133% while bare |0⟩ stays flat, exactly as relaxation predicts.
- **Feedforward correction works.** In-circuit correction beats offline
  decoding of the same syndrome records at 20,480 shots per arm, every
  interval excluding zero, and the benefit is attributable to the
  correction rather than to the conditional-control path.
- **Ratios survive drift that absolute rates do not.** Between windows,
  bare and encoded error each moved 25–31%; their ratio moved 11%.

---

## Why this exists

This is the third study in the IRMB program, and the reason for all of it
is the same: taking coursework and reading and turning it into something
that actually runs on hardware.

[Design 5](https://github.com/billyrdavis1985-bot/IRMB_Phase7G_Design5_QuantumCausality)
hit calibration drift as a confound it could not isolate.
[QNN-P1](https://github.com/billyrdavis1985-bot/IRMB_QNN-P1_DriftArchive_HardwareValidation)
turned that drift into a measurement instrument: a Raspberry Pi 5 polling
IBM's calibration API hourly since June 2026, now holding 707 unique
cycles for one device and 786 for another. QEC-P1 asked whether that
archive is good for anything beyond describing what already happened.

The answer is no, in a specific and measurable way — and getting there
required building a working distance-3 code with feedforward correction,
which is the part no course teaches, because it is operational rather
than theoretical.

---

## What is in here

```
PAPER.md              full write-up
PREREGISTRATION.md    staged preregistration, 8 amendments, 5 deviations
REPRODUCE.md          how to re-run everything, by access level
runs/README.md        every job ID with device, date and role
runs/                 immutable counts and job stamps
qec/                  the package (code, decoder, probes, runners, analysis)
figures/              the four figures
data/snapshots_*/     converted calibration archive (gitignored; see REPRODUCE)
```

---

## How this was done

**Staged preregistration.** A Stage A engineering pilot with an explicit
forbidden-analyses list — enforced in code, not left to discipline — then
a Stage B commit fixing the matrix and the analysis model before any
confirmatory run. Eight amendments and five deviations, each timestamped
before the run it governs.

**Gates that could fail, and did.** The probe-validity gate was applied to
the probe method with the same threshold that had already killed the
archive method. It failed twice. Those two runs cost 54 QPU-seconds
between them and are the reason the rest of the study is interpretable.

**Errors are published.** [Section 9 of PAPER.md](PAPER.md) lists seven,
including a parser bug that made a hardware check read 0.9043 where the
truth was 0.1582, a break-even result voided because a control arm was
never duration-matched, a proposed mechanism refuted by the analysis that
generated it, and an underpowered test whose null was briefly mistaken
for a reversal.

**Platform reality is in the record.** Over twelve days: an 83-hour
fleet-wide calibration freeze, a backlog of 24,668 pending jobs that made
one device unusable for a week, a transient authentication failure, and a
maintenance window. The backend migration this forced is documented as a
preregistration amendment, declared before any data on the new device was
collected.

---

## Limitations, stated plainly

Pilot estimation class — no confirmatory superiority claim is made
anywhere. The policy comparison rests on three discordant sessions. All
confirmatory sessions ran under a single frozen calibration cycle, so the
pre-declared fresh-versus-stale analysis is not evaluable. The stability
test covers two patches, not the stability of the ranking across eight,
which is what selection actually depends on. Single device for the
reported results. Every suppression figure is logical **bit-value** error
in a computational-basis memory — no phase-coherence claim is made or
implied.

---

## Next

If prior measurement cannot track the device, the remaining option is
measurement from inside the running computation. A repetition code
already produces a syndrome stream at every round, on the same qubits, at
the same moment, with no measure-to-act gap. This program has an unusual
position from which to test it: an independent external telemetry stream,
months long, to compare the internal record against.

---

## License

MIT (code). Independent Research in Multi-agent Benchmarking (IRMB),
Hudson Forge Technologies LLC — self-funded.
