# hf-critic — Hudson Forge Reasoning Critic

**Fine-tuning open-source LLMs into reasoning-process evaluators** — models that
judge the *quality of reasoning* behind an answer, not just whether the answer
is correct. Part of the IRMB research program at Hudson Forge Technologies LLC,
and developed as an MLOps coursework project.

---

## Overview

A reasoning critic takes a question and a candidate response and returns a fixed
assessment contract:

```
VERDICT: sound | flawed | unsound
STEP ANALYSIS: ...
SEVERITY: 1-5
REVISED ANSWER: ... (if flawed)
```

The project fine-tunes small, open-weight models into this role using a corpus
of hand-written critique examples mixed with external instruction data, then
evaluates them against a held-out benchmark reserved as a contamination
firewall. Two models were trained on identical data and compared head-to-head.

The intended use is as **lightweight, local, specialist verification
components** — a cheap always-on reasoning check, not a primary model.

## Results

| model            | verdict_rate | structure_rate | trap_detection | mean_score_3 |
|------------------|--------------|----------------|----------------|--------------|
| base Qwen3-8B    | 0.525        | 0.500          | 0.975          | 2.000        |
| tuned Qwen3-8B   | 0.950        | 0.950          | 0.900          | 2.800        |
| base Mistral-7B  | 1.000        | 0.950          | 0.800          | 2.750        |
| tuned Mistral-7B | 1.000        | 1.000          | 0.850          | 2.850        |

Evaluated on a 40-question stratified holdout. See
[`experiments.md`](experiments.md) for full run logs and per-category deltas.

**Headline finding.** Fine-tuning pulled both models toward the capability
level embedded in the training data — from opposite directions. Qwen's trap
detection came *down* (0.975 → 0.900, mild forgetting) while Mistral's came
*up* (0.800 → 0.850, a gain): they converged toward the corpus. Format proved
base-dependent: Mistral followed the output contract from the system prompt
alone (base verdict rate 1.000), while Qwen needed the fine-tune to learn it
(0.525 → 0.950). At n=40 a 0.05 delta is two questions, so the convergence is
consistent but not statistically proven. The tuned models also show
**complementary, uncorrelated blind spots** — Mistral strong where Qwen is
weakest (frontier / meta / quantum), Qwen strong where Mistral slips
(counterfactual) — which argues for running both as cross-checks rather than
selecting one.

## Repository layout

```
hf-critic/
├── README.md              # this file
├── experiments.md         # detailed run logs, findings, next steps
├── prepare_corpus.py      # build unified ChatML corpus (own + external), pinned manifest
├── reserve_holdout.py     # reserve stratified eval set (contamination firewall)
├── train_critic.py        # QLoRA fine-tune; model-agnostic via --chat-template
├── eval_critic.py         # before/after + model-vs-model scoring on the holdout
├── export_gguf.py         # quantize merged model to GGUF for serving
├── Modelfile              # Ollama config (system prompt + inference params)
├── seed_examples.jsonl    # 38 hand-written critique examples (12 categories)
├── eval_holdout.txt       # reserved HF-IQR question IDs — never trained on
└── corpus/
    └── manifest.json      # pinned dataset revisions + run config (reproducibility anchor)
```

Large artifacts (`outputs/`, `*.gguf`, generated corpus splits) are gitignored —
the code and manifests reproduce them.

## Pipeline

| stage | script | output |
|-------|--------|--------|
| build corpus | `prepare_corpus.py` | unified ChatML JSONL + pinned `manifest.json` |
| reserve eval set | `reserve_holdout.py` | `eval_holdout.txt` (stratified) |
| train | `train_critic.py` | QLoRA adapter + merged 16-bit model |
| evaluate | `eval_critic.py` | before/after scores, model-vs-model compare |
| deploy | `export_gguf.py` + `Modelfile` | GGUF served via Ollama |

## Quickstart

```bash
# 1. build the training corpus (own examples + external mix)
python prepare_corpus.py --out ./corpus --local seed_examples.jsonl

# 2. reserve the eval holdout — BEFORE training
python reserve_holdout.py

# 3. train (Qwen shown; swap --model + --chat-template for Mistral)
python train_critic.py --model unsloth/Qwen3-8B-unsloth-bnb-4bit \
  --chat-template qwen3 --out outputs/critic-qwen3-8b --upsample 20

# 4. evaluate base vs tuned, or model vs model
python eval_critic.py --model <path> --tag <name> --chat-template <tmpl>
python eval_critic.py --compare <tag_a> <tag_b>

# 5. export for serving
python export_gguf.py --model outputs/<run>/final --out outputs/<run>/gguf
ollama create critic -f Modelfile && ollama run critic
```

The train and eval scripts are model-agnostic via `--chat-template` (`qwen3`,
`mistral`); adding a base is a one-flag change plus a marker entry.

## Reproducibility

- **Pinned inputs.** `prepare_corpus.py` records exact dataset revisions in
  `corpus/manifest.json`; every corpus is rebuildable from it.
- **Contamination firewall.** The HF-IQR benchmark is reserved as the *eval
  instrument* (`eval_holdout.txt`) and never used as training data, so the
  before/after comparison is honest.
- **Seeded runs.** Training and holdout selection are seeded.
- **Controlled comparison.** The Qwen vs Mistral study holds corpus, config,
  epochs, seed, and holdout constant; the only variable is the base model.

## Methodology principles

- **Held-out evaluation** — the benchmark is never in the training set.
- **Honest deltas** — results reported base-vs-tuned and model-vs-model, with
  regressions and tradeoffs stated, not hidden (e.g. the format-vs-capability
  tradeoff, the frontier-reasoning role drift).
- **Qualitative verification** — outputs are spot-read, not trusted on scorer
  numbers alone; format adherence is not conflated with reasoning quality.
- **Local upsampling** — the small hand-written set is weighted (not merely
  concatenated) against the external data so it shapes behavior without being
  drowned out.

## Program lineage

- **HF-IQR (V1-V3)** established the multi-model council methodology for
  AI critique-behavior analysis and produced the reasoning benchmark reused here
  as a held-out eval instrument:
  [V1](https://github.com/billyrdavis1985-bot/-IRMB_HF-IQR_ReasoningBenchmark) ·
  [V2](https://github.com/billyrdavis1985-bot/HF-IQR-V2-Hudson-Forge-Intelligence-and-Reasoning-Benchmark) ·
  [V3](https://github.com/billyrdavis1985-bot/HF-IQR-V3).
- **hf-critic** turns that analysis line into a *component*: distilling
  critique behavior into small local models intended as specialist verification
  reflexes for downstream agent work (Forge Agent / AURION) and the Hudson
  Forge cluster.

## Related IRMB repositories

The reasoning benchmark used here as a held-out eval instrument:

- [HF-IQR V1](https://github.com/billyrdavis1985-bot/-IRMB_HF-IQR_ReasoningBenchmark)
- [HF-IQR V2](https://github.com/billyrdavis1985-bot/HF-IQR-V2-Hudson-Forge-Intelligence-and-Reasoning-Benchmark)
- [HF-IQR V3](https://github.com/billyrdavis1985-bot/HF-IQR-V3)

## Citation

```
Davis, B. (2026). hf-critic: Fine-tuned reasoning-process evaluators as
local verification specialists. Hudson Forge Technologies LLC.
https://github.com/billyrdavis1985-bot/hf-critic
```

## License

Apache 2.0. See [LICENSE](LICENSE).

---

*Experiment. Measure. Refine. Repeat. — Hudson Forge Technologies · IRMB Research Program*
