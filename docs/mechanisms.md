# Mechanisms

This document describes, layer by layer, the mechanisms of POLITICKER that this repository implements in reference form. It uses the terms of the proposal and its Technical Appendix.

## Data normalization layer

Sources differ in format, actor attribution and reporting conventions. The normalization layer converts each source into a common unit record: an identifier, the source, the date, actor attributes where available, context attributes, and a link to the original passage. A versioned segmentation step divides documents into the units that are coded, such as speeches.

*In this repository:* the demonstration pipeline (`src/politicker_ref/pipeline.py`) splits UK Hansard debates and US Congressional Record items into speeches. It writes each speech as a unit record with these fields:
- an identifier
- the jurisdiction and chamber
- the date
- the speaker
- the debate title
- how the unit was selected
- a link to the source

The segmenters' versions are frozen into the pipeline plan. See [declarative definitions](declarative-definitions.md).

## LLM coding layer

The Technical Appendix names four operational safeguards. They share one design principle, methodological friction: the infrastructure makes methodological judgement explicit, auditable and testable rather than automating it away.

### Snippet-level precision

Models evaluate individual segments of text in isolation. The model never navigates or interprets a corpus. Each call receives one text unit, together with the codebook, and returns one code, so every output is grounded in a specific, identifiable passage that a human coder can check.

*In this repository:* `politicker-ref run` sends one unit per call (`src/politicker_ref/run.py`). The demonstration pipeline makes each unit one speech by one speaker.

### Schema-constrained output

Each coding scheme is compiled into a Pydantic schema at run time, with the scheme's allowed codes as an enumerated type. Every response is validated against the schema before it is stored. A refusal or an answer outside the codebook is rejected and retried, never stored. This separates errors of format and category from the substantive question of whether the model codes correctly, which is then measured against human coders.

The reference implementation supports two routes:
- **Decision models,** such as TypeSafe Jev. These return one option from a predefined answer space with a probability for every option, rather than generating text. The codebook's codes become the answer space, and the probabilities give a direct measure of coding uncertainty.
- **Structured output.** Any model with an OpenAI-compatible interface receives the compiled schema through its structured-output interface.

*In this repository:* `Codebook.output_model()` and `Codebook.json_schema()` in `src/politicker_ref/codebook.py`; the providers in `src/politicker_ref/providers.py`.

### Accessible parameter control

Researchers define coding schemes and trace full data provenance without programming. In the prototype this is done through web forms. In this repository a codebook is a short, readable file. It names the theory, the instruction to coders, each code with its definition, the model and its parameters, and the pre-stated review thresholds.

Before a run, the codebook is frozen into a canonical snapshot identified by a SHA-256 hash, and every output records that hash. As a result:
- **No silent overwrites.** A revised codebook writes to a new directory, and earlier versions' outputs are kept.
- **Comparable versions.** Any two versions can be compared unit by unit.
- **Checked replays.** Recorded outputs replay only under the exact codebook version that produced them.

Each output also records:
- the provider
- the requested model and the dated model version that answered
- the probability of every option, where available
- token usage, so that measurement quality can be reported alongside cost

### Iterative ad hoc analysis

Researchers rerun analyses on subsets of a corpus without reprocessing the whole dataset:
- **Pilot runs** code a small batch before the full run.
- **Resumed runs** skip units already coded under the same codebook version.
- **Subset reruns** apply a codebook only to units an earlier run coded a particular way, most importantly the agreed residual. Recoding the residual with a rival theory's codebook shows whether an anomaly is specific to the focal theory.

*In this repository:* `--limit`, resumption by default, and `--from-outputs … --only-codes residual`.

### Model performance assessment

The model interface is replaceable. The same codebook runs against a decision model through OpenRouter, or against any OpenAI-compatible endpoint. That includes open-weight models served locally with Ollama or vLLM, which keeps confidential material on the researcher's own machine. Models from different families can code the same units. Because model errors are correlated, the human-coded benchmark, not cross-model agreement, is the reference standard.

## Human coding layer

The theoretical accommodation review uses three measures, each against pre-stated thresholds, to separate measurement failure from theoretical misfit (Table 1):
- human-human reliability
- model-human agreement
- the agreed residual

Model performance against human-coded labels is also reported with precision, recall and F1. See [the accommodation review](accommodation-review.md).

The human coding interface, sampling with inclusion probabilities, and the codebook revision log are planned. See [scope and roadmap](scope-and-roadmap.md).
