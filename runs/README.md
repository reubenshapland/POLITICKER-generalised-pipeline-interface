# Runs

Each run is written under the hash of the codebook version or pipeline plan that produced it, so a revised codebook never overwrites earlier outputs.

- `runs/<codebook-id>/<hash>/` holds the frozen codebook (`codebook.snapshot.json`) and the model outputs (`outputs.jsonl`). Reproduce a run with `politicker-ref run … --replay <outputs.jsonl>`.
- `runs/pipelines/<pipeline-id>/<hash>/` holds the frozen pipeline plan and the unit records (`units.jsonl`). The demonstration pipeline's unit records are included; they are produced without calling a model.

No model outputs are included in this release. Model outputs for the benchmark sample will be added with the replication package described in [scope and roadmap](../docs/scope-and-roadmap.md).
