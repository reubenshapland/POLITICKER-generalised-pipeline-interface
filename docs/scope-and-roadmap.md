# Scope and roadmap

## What this repository is

POLITICKER has three layers: data normalization, human coding and LLM coding. A working prototype of the data normalization and LLM coding layers is in use in two research projects, one in organizational science and one in political science. The prototype is part of a commercially developed system, so its code is not released.

This repository is a standalone reference implementation of the measurement core. It shows how each layer works on public UK and US parliamentary transcripts, so that every step can be inspected and reproduced, and so that researchers can apply a codebook to text units they supply.

## How this repository relates to Table A1

The first two columns reproduce Table A1 of the Technical Appendix, which reports the status of the POLITICKER prototype. The third column shows what this repository implements in reference form.

| Component | Status (Table A1) | Reference version in this repository |
|---|---|---|
| Coding schemes set through web forms and compiled into validated output schemas | Built | Codebook files compiled into validated output schemas |
| Revert and rerun by batch, and reset of failed batches | Built | Resumable runs, and reruns on selected subsets of units |
| Segment provenance (offsets, hash, segmenter version) and saved model requests and responses | Built | Codebook snapshot hash, model, served model version, probabilities and usage stored with every output |
| Token usage and cost logging for each call | Built, Gemini only | Token usage stored with every output |
| Line-referenced grounding of outputs | Built, except classification | Not applicable: each output is tied to one speech |
| Per-job access control, API, and CSV export | Built | Not included |
| Ingestion of the four legislatures (nine record series) | Built at document level | Small collection scripts for public UK and US records |
| Common unit record with speaker, role, and setting | Planned | Unit records produced by the demonstration pipeline |
| Speech- and turn-level segmentation | Specified, not built | Speech segmenters for UK Hansard and the US Congressional Record |
| Model selection per job, open-weight models, and models from several families | Planned | A decision-model provider, and an OpenAI-compatible provider that includes local open-weight models |
| Human coding interface, sampling with inclusion probabilities, and reliability reporting | Planned | Reliability reporting only |
| Versioned codebooks, revision log, and accommodation reports | Planned | Versioned codebook snapshots and accommodation reports; no revision log |
| Self-service accounts and document upload for the hosted service | Planned | Not included |

## What is not released, and why

The prototype's code is not released: the acquisition and parsing of the four legislatures' records, normalization, orchestration, storage and the interface. These form part of a separate, commercially developed system. Nothing needed to reproduce the measurement is withheld. Anyone can apply a codebook to the sample, or to their own text units, with any supported model, and compute every element of the accommodation report.

## What we hope to do

By early 2027, the plan is to complete POLITICKER and a demonstration that applies an institutional theory codebook to AI regulation discourse in four legislatures. The priorities are:
1. speech-level segmentation, as the prototype codes segments of up to 30,000 characters
2. the human coding layer
3. per-job model selection, including open-weight models
4. self-service hosted access

Three controls will test Table 1.

As the demonstration is completed, this repository will add a replication package. It will contain the benchmark sample linked to its public source records, the human codes, the model outputs for the coded units, and the codebook revision logs. The repository will be archived with a DOI at each release. Academic researchers will have free access to the hosted coding interface.

## Licences

- Code: [PolyForm Noncommercial 1.0.0](../LICENSE). Free for research, teaching and other non-commercial use.
- Documentation and example codebooks: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- Data: UK Parliament material under the [Open Parliament Licence v3.0](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/); US Congressional Record material in the public domain.
