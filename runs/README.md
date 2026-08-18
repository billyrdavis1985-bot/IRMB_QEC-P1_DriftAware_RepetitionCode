# `runs/` — evidence provenance

Every hardware job executed for QEC-P1, what it was for, and what it does
and does not support. Read this before interpreting anything in this
directory.

**Total metered: 438 QPU-seconds (7.30 minutes) across 26 completed jobs**,
against a preregistered 40-minute cap. One job (Q-D) was queued at the time
of writing.

---

## The critical distinction: two devices

The study **migrated backends mid-flight**. This is not cosmetic.

| | device | sessions | status |
|---|---|---|---|
| **Pilot** | `ibm_fez` | session 1 | **excluded from pooled analysis** |
| **Study** | `ibm_marrakesh` | sessions 11-14, all supplements | the reported results |

`ibm_fez` accumulated **24,668 pending jobs** following an 83-hour
fleet-wide calibration freeze (2026-08-06 to 2026-08-10) and became
unusable: a 1-PUB, 10-shot diagnostic job queued for five days. Amendment
A4 migrated the study to `ibm_marrakesh` on 2026-08-14, **before any
marrakesh data was collected or examined**.

Session numbering reflects this: **sessions 1 (fez) and 11-14 (marrakesh)**
are deliberately non-contiguous so no file can be mistaken for the other
device. Session 1's data is retained and reported as a hardware pilot
demonstrating the apparatus end to end. It is **never pooled** with
marrakesh sessions — cross-session comparison requires one device.

---

## Job ledger

### ibm_fez (pilot and platform diagnostics) — 6 jobs, 48 s

| job id | date | QPU s | role |
|---|---|---|---|
| `d9r5g4pdsedc73ag7hmg` | 08-07 | 3 | Stage A cost pilot. Patch (140,141,142,143,144), 7 circuits x 512. First measured cost. Injected-X 0.1582, corrected — **after** the D-A1 parser fix; the first analysis pass of this same job reported 0.9043 and was wrong. |
| `d9r7ihopdb6s73e4i4og` | 08-07 | 4 | Session 1 probe, 8 candidates. |
| `d9r7lr0pdb6s73e4i950` | 08-07 | 35 | Session 1 main, 30 circuits x 4096. **PILOT ONLY.** |
| `d9sekvpdsedc73ahmb70` | 08-09 | 0 | Session 2 probe, cancelled after 24 h queued. No data. |
| `d9t3ej1dsedc73aie9e0` | 08-10 | 4 | Session 2 probe, resubmitted. Executed ~8 days later. **No matching main job; not used.** Evidence of queue latency only. |
| `d9v40ano3ppc73ajptm0` | 08-13 | 2 | Minimal queue diagnostic: 1 PUB, 1 qubit, 10 shots. Queued 5 days. **Not science** — it established that the stall was device-side, not job-size or code related. |

### ibm_marrakesh (the study) — 20 jobs, 390 s

| job id | date | QPU s | role |
|---|---|---|---|
| `d9vnvst0vrcc73bpi050` | 08-14 | 0 | Reachability test. Completed instantly while fez stalled; motivated A4. |
| `d9vp4ano3ppc73akkscg` | 08-14 | 3 | Stage A cost pilot (marrakesh). Patch (2,3,4,5,6). Injected-X 0.1680, corrected. Cost figures do not carry across devices, so this was re-measured. |
| `d9vp9hv2sl0c73bm88r0` | 08-14 | 4 | Session 11 probe. |
| `d9vp9k50vrcc73bpjqtg` | 08-14 | 36 | Session 11 main. Discordant; policies shared 4 of 5 qubits. |
| `da05c20b1g9c73a9e62g` | 08-15 | 4 | Session 12 probe. |
| `da05c4fo3ppc73al32vg` | 08-15 | 36 | Session 12 main. Discordant; disjoint patches. |
| `da0gj3vo3ppc73alfd7g` | 08-15 | 4 | Session 13 probe. |
| `da0gj772sl0c73bn2jsg` | 08-15 | 36 | Session 13 main. **CONVERGENT** — both policies chose (1,2,3,4,5). Carries no policy contrast; **excluded from the Q-A' paired estimate** per preregistration, retained as convergence-rate data. |
| `da0r6nkdedkc73eq93ag` | 08-16 | 4 | Session 14 probe. |
| `da0r6r63kjvs7385vh5g` | 08-16 | 36 | Session 14 main. Discordant; disjoint patches. |
| `da0rpbqein7c73bclnt0` | 08-16 | 37 | **Q-B supplement, window 1.** Duration-matched BARE; delays 5272/5284/5281 dt. Supersedes the void S values from sessions 11-14 (see D-B3). |
| `da15s563kjvs7386bc00` | 08-16 | 4 | G6-extended probe, all 8 candidates. |
| `da15s5mg52gs73cl87kg` | 08-16 | 11 | G6-extended deploy, all 8 candidates. Within-session rho **-0.072** — probe does not predict logical error. |
| `da1od4e3kjvs738708t0` | 08-17 | 28 | Probe v2 probe, 4096 shots (16x precision of v1). |
| `da1od4m3kjvs738708tg` | 08-17 | 11 | Probe v2 deploy. rho **-0.335**. G6 negative is structural, not a probe-design artifact. |
| `da1ohmmg52gs73clta00` | 08-17 | 16 | Q-E stability, job A. 6 interleaved repeats x 2 patches. |
| `da1oiee3kjvs73870epg` | 08-17 | 16 | Q-E stability, job B. Submitted after A returned. |
| `da1onte3kjvs73870l80` | 08-17 | 37 | **Q-B supplement, window 2.** 12/12 cells replicate direction. |
| `da1qa6ug52gs73clvp30` | 08-17 | 13 | DUMMY_FF attribution at 4096 shots. **UNDERPOWERED (~5x)** and inconclusive; retained because it shows what an underpowered test looks like beside a powered one. |
| `da1qf4iein7c73bdom90` | 08-17 | 54 | **Powered E4 re-test**, 20,480 shots/arm. E4 confirmed, intervals exclude zero in all three patches; attribution to correction rather than control path. |
| `da2ct4rotlns7398cc30` | 08-18 | queued | Q-D rounds sweep, 1/3/5 rounds. Delays 2392/5272/8152 dt (9.57/21.09/32.61 us). |

---

## Files that are superseded or void

- **`session_11-14_counts.json` BARE cells.** `stage_b` called
  `tier0.build_bare(state)` without `delay_dt`, which defaults to 0, so
  the BARE arm ran as prepare-and-measure (depth 2) against a three-round
  encoded circuit (depth 74). Any S computed from these is **void** — see
  deviation D-B3. The Q-B supplements replace them. The encoded arms in
  these files are unaffected and are used for Q-A' and E4.
- **`stage_a_result.json` (first pass).** Reported injected-X 0.9043 from
  a parser that read one classical register instead of four (D-A1). The
  committed file is the corrected re-analysis; no QPU was respent.
- **`g5_marrakesh.json` (first pass).** An initial G5 run compiled
  marrakesh-derived patches against the **fez** target because the backend
  was hardcoded. Void; the committed file is the corrected run.

---

## What the evidence supports, and what it does not

**Supports:**
- Five selection instruments failed to predict d=3 repetition-code logical
  error (archive composite twice, probe v1, probe v2, archived-feature
  diagnosis).
- Q-B: encoding beats a duration-matched physical qubit for |1_L> and
  loses for |0_L>, replicated across two windows, 12/12 cells by direction.
- E4: active correction beats offline decoding, confirmed at 20,480
  shots/arm with intervals excluding zero, attributable to correction.
- Q-E: within-job behaviour is binomially stable; absolute logical error
  moves ~31% over ten minutes and 25-31% between windows, while within-job
  **ratios** move only ~11%.

**Does not support:**
- Any confirmatory superiority claim for Q-A'. Three discordant sessions,
  session-to-session sd 0.067 against SESOI 0.010.
- Any claim about phase coherence or a generally protected logical qubit.
  Every suppression figure here is logical **bit-value** error in a
  computational-basis memory.
- Pooling fez session 1 with marrakesh sessions.
- The A3 fresh-versus-stale sensitivity analysis: all marrakesh sessions
  ran under one frozen calibration cycle, so it is **not evaluable**.

---

## Platform events affecting this record

| dates | event |
|---|---|
| 08-06 to 08-10 | 83-hour fleet-wide calibration freeze (`ibm_fez` and `ibm_marrakesh` froze within 2 minutes of each other) |
| 08-09 to 08-18 | `ibm_fez` backlog reaching 24,668 pending; a 4-second job waited ~8 days |
| 08-09 | transient auth failure; recovered from the collector's stored credential |
| 08-14 to 08-16 | `ibm_marrakesh` calibration frozen at 2026-08-14 11:04 through sessions 11-14 |
| 08-18 | `ibm_marrakesh` and `ibm_kingston` in maintenance; `ibm_fez` recovered to 0 pending |

These are not incidental. The study's central finding is that device state
moves faster than prior measurement can track it; the platform record shows
that measurement access is itself frequently unavailable.
