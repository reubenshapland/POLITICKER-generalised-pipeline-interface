# Scope and roadmap

## What this repository is

The research contribution of GET is a hosted interface. Through it, researchers without programming skills can apply theory-driven codebooks to large corpora, validate the coding against human coders, and review whether a theory accommodates a phenomenon. That interface is the main deliverable of the proposed development (Stage 2). It is not yet available.

This repository is the proof of concept of its measurement core. It implements, in reference form, the mechanisms on which the interface will rest:
- coding one unit per call
- a constrained answer space
- versioned codebook snapshots
- iterative and subset reruns
- per-output provenance
- the accommodation review

It runs on public UK and US parliamentary transcripts, so every step can be inspected and reproduced.

## What is public and what is not

| Component | In this repository |
|---|---|
| Codebook format, schema compilation and snapshot hashing | Yes |
| Model providers: a decision model via OpenRouter; any OpenAI-compatible endpoint, including local open-weight models | Yes |
| Reliability, agreed residual and Table 1 interpretation | Yes |
| Public sample of 40 units and the script that drew it | Yes |
| 23 UK and US transcripts, the script that collected them, and a miniature declarative pipeline that segments, filters and codes them | Yes |
| Example codebook (institutional pillars) | Yes |
| Recorded model outputs for the sample | Yes, once recorded |
| Description of the declarative pipeline definitions | Yes; the production runtime is not included |
| Acquisition and parsing of the four legislatures' records | No |
| Normalization, orchestration, storage and the production runtime | No |
| The hosted interface | No; planned |

The production components are excluded because they form a separate, commercially developed system. Nothing needed to reproduce the measurement is withheld. Anyone can rerun a codebook on the sample, or on their own text units, with any supported model, and compute every signal of the accommodation review.

## Current state of the wider infrastructure

| Component | Status |
|---|---|
| Ingestion of the four legislatures' proceedings | Built, at document level |
| Configurable extraction with schema-constrained output, per-batch revert and rerun, and cost logging | Built, in an internal prototype |
| Runtime for declarative pipeline definitions, with a decision model | In development; a first classification pipeline runs |
| Speech-level segmentation | Planned |
| Human coding interface, sampling with inclusion probabilities, reliability reporting | Planned |
| Codebook revision log and accommodation reports | Planned |
| Hosted interface with self-service access for researchers | Planned |

## Roadmap (Stage 2, January to May 2027)

1. Speech-level segmentation across the four legislatures, so that each coded unit is one contribution by one speaker.
2. The human coding layer: a coding interface, samplers with stored inclusion probabilities, reliability reporting and the codebook revision log.
3. Benchmark coding of a stratified sample by two trained coders, and model assessment against it, with decision models, open-weight models and models from several families.
4. The demonstration: an institutional theory codebook applied to AI regulation discourse in the four legislatures, with three controls testing whether the review separates its categories.
5. Hosted access for researchers, and a replication package for the demonstration archived with a DOI. The package will hold the benchmark sample, the human codes, the model outputs and the codebook revision logs.

## Licences

- Code: [PolyForm Noncommercial 1.0.0](../LICENSE). Free for research, teaching and other non-commercial use.
- Documentation and example codebooks: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- Sample data: UK Parliament Hansard, under the [Open Parliament Licence v3.0](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).
