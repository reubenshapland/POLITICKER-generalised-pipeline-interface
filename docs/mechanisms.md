# Measurement mechanisms

The General Extraction Tool (GET) is the research infrastructure proposed in the submission. Its purpose is to let researchers without programming skills apply a theory-driven codebook to a large corpus, check the result against human coders, and decide whether the theory accommodates the phenomenon. This document describes the mechanisms that make the coding auditable and reproducible. Each one is implemented, in reference form, in this repository.

## 1. One unit per model call

The model never navigates or interprets a corpus. Each call receives exactly one text unit, such as a speech, together with the codebook, and returns one code. Every output is therefore tied to a specific, identifiable passage of source text, and can be checked by a human coder against that passage alone.

*In this repository:* `getref run` sends one unit per call (`src/getref/run.py`), and the demonstration pipeline first splits transcripts into speeches so that each unit is one contribution by one speaker (`src/getref/pipeline.py`).

## 2. A constrained answer space

A model can only answer with a code that the codebook defines. Two routes are supported:

- **Decision models.** Models such as TypeSafe Jev take context and a choice question and return one option from a predefined answer space, with a probability for every option. They do not generate free text. The codebook's codes become the answer space, and the probabilities give a direct measure of coding uncertainty for each unit.
- **Structured output.** For general-purpose models, the codebook is compiled into a schema in which the code field is an enumeration. The schema is passed to the provider's structured-output interface, and every response is validated against it before it is stored.

In both routes, a refusal or an answer outside the codebook is rejected and retried, never stored. This separates one source of measurement error, inconsistent output formats and invented categories, from the substantive question of whether the model codes correctly. The substantive question can then be measured against human coders.

*In this repository:* `Codebook.output_model()` and `Codebook.json_schema()` in `src/getref/codebook.py`; both providers in `src/getref/providers.py`.

## 3. Versioned codebooks

Before a run starts, the codebook is frozen into a canonical snapshot and identified by a SHA-256 hash. The snapshot covers the definitions, the instructions, the model and its parameters, and the review thresholds. Every output records the hash of the snapshot that produced it.

Consequences:

- **No silent overwrites.** A revised codebook has a new hash and writes to a new run directory. The outputs of earlier versions are kept.
- **Comparable versions.** Any two versions can be compared unit by unit, and the revision history shows how far the theory had to be changed to fit the data.
- **Checked replays.** Recorded outputs can be replayed only under the exact codebook version that produced them.

*In this repository:* `Codebook.snapshot_hash()`; `runs/<codebook-id>/<hash>/codebook.snapshot.json`.

## 4. Iterative analysis without reprocessing

Researchers refine a codebook on small batches before applying it to a full corpus, and return to subsets of the corpus as the analysis develops:

- **Pilot runs** code only the first N units.
- **Resumed runs** skip units already coded under the same codebook version, so an interrupted run continues where it stopped.
- **Subset reruns** apply a codebook only to units an earlier run coded a particular way. An example is rerunning the agreed residual with a rival theory's codebook. Inductive coding of the residual then proposes candidate constructs.

*In this repository:* `--limit`, resumption by default, and `--from-outputs … --only-codes residual`.

## 5. Provenance for every output

Each stored output records:
- the unit identifier and the codebook snapshot hash
- the provider, the requested model and the dated model version that actually answered
- the code, and the probability of every option where the model provides them
- token usage and a timestamp

Token usage lets researchers report cost alongside measurement quality. They can then choose the least expensive model that reaches acceptable agreement with human coders.

## 6. A replaceable model layer

Models change quickly, so the infrastructure does not depend on any one of them. The same codebook runs against a decision model through OpenRouter, or against any endpoint that offers JSON Schema structured output. That includes open-weight models served locally with Ollama or vLLM, which keeps confidential material on the researcher's own machine. Models from different families can code the same units. Because model errors are correlated, human-coded benchmarks, not cross-model agreement, remain the reference standard.

## What is not in this repository

The production system around these mechanisms is not released. That covers acquisition and parsing of the four legislatures' records, normalization, orchestration, storage and the planned hosted interface. See [scope and roadmap](scope-and-roadmap.md).
