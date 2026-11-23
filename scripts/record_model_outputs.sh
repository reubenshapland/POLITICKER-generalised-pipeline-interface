#!/usr/bin/env bash
# Record real model outputs for the repository, then commit them.
#
# Needs OPENROUTER_API_KEY (with access to typesafe/jev-1.14) in the environment.
# Codes the 40-unit sample and the speeches kept by the demonstration
# pipeline: roughly 290 decision-model calls in total. Safe to rerun: units
# already coded under the same codebook version are skipped.
#
# Usage:
#   OPENROUTER_API_KEY=... bash scripts/record_model_outputs.sh

set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "Set OPENROUTER_API_KEY first." >&2
  exit 1
fi

python -m pip install -q -e ".[test]"
python -m pytest -q

getref run codebooks/institutional-pillars-ai.yaml data/sample_units.jsonl
getref pipeline pipelines/ai-discourse-uk-us.yaml data/transcripts.jsonl

git add runs
git commit -m "Record Jev outputs for the sample and the demonstration pipeline"
echo "Done. Push with: git push"
