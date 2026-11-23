"""Generate SYNTHETIC human codes and model outputs for demonstrating `politicker-ref review`.

These data are invented. No human has coded the sample yet: benchmark coding
by trained coders is part of the planned demonstration. They exist only so that
the review step can be run end to end and its output format inspected. They
support no substantive conclusion.

Usage:
    python examples/make_synthetic.py
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from politicker_ref.codebook import load_codebook  # noqa: E402

SEED = 20261123
AGREEMENT = 0.85  # probability that coder B (and the model) repeat coder A's code


def main() -> None:
    codebook = load_codebook(ROOT / "codebooks" / "institutional-pillars-ai.yaml")
    codes = list(codebook.question.options)
    weights = [0.35, 0.2, 0.15, 0.2, 0.1]  # regulative, normative, cultural_cognitive, residual, not_relevant
    rng = random.Random(SEED)
    units = [json.loads(line) for line in open(ROOT / "data" / "sample_units.jsonl", encoding="utf-8")]

    def perturb(code: str) -> str:
        return code if rng.random() < AGREEMENT else rng.choice([c for c in codes if c != code])

    rows, outputs = [], []
    for unit in units:
        a = rng.choices(codes, weights)[0]
        rows += [
            {"unit_id": unit["unit_id"], "coder": "synthetic_coder_a", "code": a},
            {"unit_id": unit["unit_id"], "coder": "synthetic_coder_b", "code": perturb(a)},
        ]
        outputs.append(
            {
                "unit_id": unit["unit_id"],
                "snapshot_hash": codebook.snapshot_hash(),
                "codebook_id": codebook.id,
                "code": perturb(a),
                "provider": "synthetic",
                "model": "synthetic",
            }
        )

    with open(ROOT / "examples" / "synthetic_human_codes.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["unit_id", "coder", "code"])
        writer.writeheader()
        writer.writerows(rows)
    with open(ROOT / "examples" / "synthetic_model_outputs.jsonl", "w", encoding="utf-8") as handle:
        for record in outputs:
            handle.write(json.dumps(record) + "\n")
    print(f"Wrote synthetic codes for {len(units)} units (snapshot {codebook.short_hash})")


if __name__ == "__main__":
    main()
