# GET reference implementation

Research artifact for the submission *A Reusable Computational Infrastructure for Phenomenon-Based Research* (Organization Science special issue "AI-Enabled Frontiers in Organizational Science").

## What this is

The submission proposes the General Extraction Tool (GET). GET is a hosted research infrastructure that lets researchers without programming skills apply a theory-driven codebook to a large corpus with large language models. They can then validate the coding against human coders, and assess whether the theory's constructs accommodate the phenomenon or whether new theory is needed.

**The hosted interface is the main deliverable of the proposed development and does not exist yet.** This repository is the proof of concept of its measurement core. It is a small, runnable reference implementation of the mechanisms the interface will rest on, applied to a public sample of parliamentary debate:

- **One unit per model call.** Every output is tied to one identifiable passage of source text.
- **A constrained answer space.** A model can only return codes the codebook defines. This works through a decision model that returns a probability for every code, or through schema-validated structured output.
- **Versioned codebooks.** Each codebook is frozen and hashed before a run, outputs record the hash, and revisions never overwrite earlier results.
- **Iterative analysis.** Pilot runs, resumable runs, and reruns on subsets, such as the agreed residual coded with a rival theory's codebook.
- **The accommodation review.** Human-human reliability, model-human agreement and the agreed residual are interpreted against pre-stated thresholds (Table 1 of the proposal).

[docs/mechanisms.md](docs/mechanisms.md) explains each mechanism, and [docs/scope-and-roadmap.md](docs/scope-and-roadmap.md) sets out what is and is not released, and why.

## Quick start

Requires Python 3.10 or later.

```bash
pip install -e ".[test]"
pytest                                                    # 24 tests, no network needed

getref validate codebooks/institutional-pillars-ai.yaml   # schema and snapshot hash
```

Reproduce the recorded model outputs exactly, without an API key:

```bash
getref run codebooks/institutional-pillars-ai.yaml data/sample_units.jsonl \
  --replay runs/institutional-pillars-ai/<hash>/outputs.jsonl --runs /tmp/replay
```

Re-execute the coding with the decision model (TypeSafe Jev, via OpenRouter):

```bash
export OPENROUTER_API_KEY=...
getref run codebooks/institutional-pillars-ai.yaml data/sample_units.jsonl --limit 5   # pilot
getref run codebooks/institutional-pillars-ai.yaml data/sample_units.jsonl             # the rest
```

Use a local open-weight model instead. Copy the codebook, set `provider: openai_compatible` and the model name, then:

```bash
export OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1   # Ollama
getref run my-codebook.yaml data/sample_units.jsonl
```

Rerun only the units an earlier run coded as residual, for example with a rival theory's codebook:

```bash
getref run rival-codebook.yaml data/sample_units.jsonl \
  --from-outputs runs/institutional-pillars-ai/<hash>/outputs.jsonl --only-codes residual
```

Run the accommodation review:

```bash
getref review codebooks/institutional-pillars-ai.yaml \
  --human examples/synthetic_human_codes.csv --outputs examples/synthetic_model_outputs.jsonl
```

**The files in `examples/` are synthetic.** No human coding has been done yet; benchmark coding is Stage 2 work. The synthetic files only show that the review runs end to end and what it reports.

## Repository map

| Path | Contents |
|---|---|
| `src/getref/codebook.py` | Codebook format, validation, schema compilation, snapshot hashing |
| `src/getref/providers.py` | Decision-model, OpenAI-compatible and replay providers |
| `src/getref/run.py` | One-unit-per-call runs, resumption, subset selection, provenance |
| `src/getref/accommodation.py` | Cohen's kappa, agreed residual, Table 1 interpretation |
| `codebooks/` | Example codebook: institutional pillars (Scott 2014) in AI regulation debate |
| `data/sample_units.jsonl` | 40 spoken contributions from the UK Commons and Lords, 2023 to 2025 |
| `scripts/build_sample.py` | The fixed query that drew the sample from the Hansard API |
| `runs/` | Recorded model outputs and the codebook snapshots that produced them |
| `examples/` | Synthetic human codes and model outputs for the review demonstration |
| `docs/` | Mechanisms, declarative pipeline definitions, the review, scope and roadmap |

## Data

The sample consists of spoken contributions from UK Parliament Hansard. It is reproduced under the Open Parliament Licence v3.0. Each unit links to its Hansard record. The links follow Hansard's documented URL format; Hansard blocks automated requests, so they have not been checked automatically. The example codebook is illustrative. It is not the confirmatory codebook for the study.

## Licences

Code is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE), which permits research, teaching and other non-commercial use. Documentation and codebooks are licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Sample data remain under the Open Parliament Licence v3.0.
