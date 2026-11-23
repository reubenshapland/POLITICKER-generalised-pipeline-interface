"""Command-line interface: ``getref validate | run | review``."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from .accommodation import format_table, review
from .codebook import load_codebook
from .providers import ProviderError, ReplayProvider, make_provider
from .run import read_jsonl, run, select_units


def cmd_validate(args) -> int:
    codebook = load_codebook(args.codebook)
    print(f"{codebook.id} v{codebook.version}: valid")
    print(f"snapshot hash: {codebook.snapshot_hash()}")
    print(f"constructs: {', '.join(codebook.question.constructs)}")
    print(json.dumps(codebook.json_schema(), indent=2))
    return 0


def cmd_run(args) -> int:
    codebook = load_codebook(args.codebook)
    units = read_jsonl(args.units)
    if args.only_codes:
        units = select_units(units, read_jsonl(args.from_outputs), args.only_codes.split(","))
    if args.limit:
        units = units[: args.limit]
    try:
        provider = ReplayProvider(read_jsonl(args.replay)) if args.replay else make_provider(codebook)
    except ProviderError as error:
        raise SystemExit(f"Error: {error}") from None
    out_dir = run(codebook, units, provider, root=args.runs, force=args.force)
    counts = Counter(r["code"] for r in read_jsonl(out_dir / "outputs.jsonl"))
    print(f"Outputs in {out_dir}")
    for code, n in counts.most_common():
        print(f"  {code}: {n}")
    return 0


def _read_human(path: str) -> dict[str, dict[str, str]]:
    coders: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            coders.setdefault(row["coder"], {})[row["unit_id"]] = row["code"]
    if len(coders) != 2:
        raise SystemExit(f"Expected exactly two human coders in {path}, found {sorted(coders)}")
    return coders


def cmd_review(args) -> int:
    codebook = load_codebook(args.codebook)
    coders = _read_human(args.human)
    a, b = (coders[k] for k in sorted(coders))
    model = {r["unit_id"]: r["code"] for r in read_jsonl(args.outputs) if r["snapshot_hash"] == codebook.snapshot_hash()}
    if not model:
        print("Warning: no model outputs match this codebook snapshot", file=sys.stderr)
    print(format_table(review(codebook, a, b, model)))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="getref", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Validate a codebook and print its snapshot hash and schema")
    p.add_argument("codebook")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("run", help="Code units with a codebook, one unit per call")
    p.add_argument("codebook")
    p.add_argument("units", help="JSONL file of text units")
    p.add_argument("--runs", default="runs", help="Output root (default: runs)")
    p.add_argument("--replay", help="Recorded outputs.jsonl to replay instead of calling a model")
    p.add_argument("--from-outputs", help="Earlier outputs.jsonl used with --only-codes")
    p.add_argument("--only-codes", help="Comma-separated codes: rerun only units coded this way in --from-outputs")
    p.add_argument("--limit", type=int, help="Code only the first N units (pilot run)")
    p.add_argument("--force", action="store_true", help="Recode units already coded under this snapshot")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("review", help="Reliability, agreed residual and Table 1 interpretation")
    p.add_argument("codebook")
    p.add_argument("--human", required=True, help="CSV with columns unit_id, coder, code (two coders)")
    p.add_argument("--outputs", required=True, help="Model outputs.jsonl")
    p.set_defaults(func=cmd_review)

    args = parser.parse_args(argv)
    if getattr(args, "only_codes", None) and not getattr(args, "from_outputs", None):
        parser.error("--only-codes needs --from-outputs")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
