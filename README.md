# POLITICKER reference implementation

Research artifact for the submission *POLITICKER: A Reusable Computational Infrastructure for Phenomenon-Based Research* (Organization Science special issue "AI-Enabled Frontiers in Organizational Science").

## What this is

POLITICKER is a reusable research infrastructure that measures *theoretical accommodation*: the degree to which the constructs of an extant theory can capture the empirically relevant content of a phenomenon without modification to its core tenets. It applies a theory's constructs to a corpus as a codebook and reports two indicators:
- the **agreed residual**: the share of relevant text units that human coders reliably agree fall outside every construct
- the **codebook revisions** needed to reach acceptable reliability

POLITICKER has three layers: data normalization, human coding and LLM coding. A working prototype of the data normalization and LLM coding layers is in use in two research projects. The Technical Appendix's Table A1 lists which components are built and which are planned.

The prototype is part of a commercially developed system and is not released. **This repository is a standalone reference implementation of the measurement core.** It is small, runnable code that shows how each layer works, so that the method can be inspected, reproduced and applied to new material:

| Layer | In this repository |
|---|---|
| Data normalization | A demonstration pipeline that splits UK and US parliamentary transcripts into speeches and turns each into a common unit record |
| LLM coding | Codebooks compiled into validated output schemas; one unit per model call; versioned codebook snapshots; per-output provenance; pilot, resumed and subset reruns; replaceable model providers |
| Human coding | The accommodation review: Cohen's kappa, the agreed residual, the Table 1 interpretation, precision, recall, F1 and confusion matrices |

[docs/mechanisms.md](docs/mechanisms.md) describes each mechanism in the terms the proposal uses. [docs/scope-and-roadmap.md](docs/scope-and-roadmap.md) maps the repository onto Table A1 and sets out what is planned.

**Models.** The prototype described in the Technical Appendix runs on Gemini 2.5 Flash-Lite. This reference implementation codes with TypeSafe Jev, the decision model the Technical Appendix identifies as a candidate for evaluation. It also runs any model with an OpenAI-compatible interface, including the open-weight models the proposal plans as the default.

## Quick start

Requires Python 3.10 or later.

```bash
pip install -e ".[test]"
pytest                                                            # no network needed

politicker-ref validate codebooks/institutional-pillars-ai.yaml   # schema and snapshot hash
```

Apply a codebook to a CSV file of text units. The file needs a `unit_id` column and the fields the codebook lists under `state_fields`:

```bash
export OPENROUTER_API_KEY=...
politicker-ref run codebooks/institutional-pillars-ai.yaml my_units.csv --limit 5   # pilot
politicker-ref run codebooks/institutional-pillars-ai.yaml my_units.csv             # the rest
```

Use a local open-weight model instead. Copy the codebook, set `provider: openai_compatible` and the model name, then:

```bash
export OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1   # Ollama
politicker-ref run my-codebook.yaml my_units.csv
```

Reproduce recorded model outputs exactly, without an API key:

```bash
politicker-ref run codebooks/institutional-pillars-ai.yaml data/sample_units.jsonl \
  --replay runs/institutional-pillars-ai/<hash>/outputs.jsonl --runs /tmp/replay
```

Run the demonstration pipeline on 23 UK and US transcripts. Without an API key, it segments and filters only, and writes the unit records to `runs/pipelines/…/units.jsonl`:

```bash
politicker-ref pipeline pipelines/ai-discourse-uk-us.yaml data/transcripts.jsonl
```

Rerun only the units an earlier run coded as residual, for example with a rival theory's codebook:

```bash
politicker-ref run rival-codebook.yaml data/sample_units.jsonl \
  --from-outputs runs/institutional-pillars-ai/<hash>/outputs.jsonl --only-codes residual
```

Produce an accommodation report:

```bash
politicker-ref review codebooks/institutional-pillars-ai.yaml \
  --human examples/synthetic_human_codes.csv --outputs examples/synthetic_model_outputs.jsonl
```

**The files in `examples/` are synthetic.** The benchmark sample has not yet been coded by human coders, which is part of the planned demonstration. The synthetic files show only that the review runs end to end and what it reports.

## Repository map

| Path | Contents |
|---|---|
| `src/politicker_ref/codebook.py` | Codebook format, validation, schema compilation, snapshot hashing |
| `src/politicker_ref/providers.py` | Decision-model, OpenAI-compatible and replay providers |
| `src/politicker_ref/run.py` | One-unit-per-call runs from CSV or JSONL, resumption, subset selection, provenance |
| `src/politicker_ref/pipeline.py` | Demonstration pipeline: speech segmentation, AI-term filter, coding step, frozen plans |
| `src/politicker_ref/accommodation.py` | Cohen's kappa, agreed residual, Table 1 interpretation, precision, recall, F1, confusion matrices |
| `codebooks/` | Example codebook: institutional pillars (Scott 2014) in AI regulation debate |
| `pipelines/` | The demonstration pipeline definition |
| `data/transcripts.jsonl` | 23 transcripts: 12 UK Hansard debates and 11 US Congressional Record items, 2023 to 2025 |
| `data/sample_units.jsonl` | 40 spoken contributions from the UK Commons and Lords, 2023 to 2025 |
| `scripts/` | The fixed queries that drew the sample and the transcripts, and the script that records model outputs |
| `runs/` | Recorded model outputs, unit records, and the codebook snapshots and pipeline plans that produced them |
| `examples/` | Synthetic human codes and model outputs for the review demonstration |
| `docs/` | Mechanisms, pipeline definitions, the accommodation review, scope and roadmap |

## Data

UK material comes from UK Parliament Hansard, under the Open Parliament Licence v3.0. US material comes from the Congressional Record through GovInfo; as a work of the US Government it is in the public domain. Half the transcripts have "artificial intelligence" in their title. The other half mention it only in the text, so the pipeline's filter applies both of its rules. Each unit links to its source record. The links follow Hansard's documented URL format; Hansard blocks automated requests, so they have not been checked automatically.

The example codebook is illustrative. The confirmatory codebook for the four-legislature demonstration will be developed with the human coding layer.

## Licences

Code is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE), which permits research, teaching and other non-commercial use. Documentation and codebooks are licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). UK data remain under the Open Parliament Licence v3.0; US data are in the public domain.
