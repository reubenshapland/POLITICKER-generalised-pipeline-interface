"""Command-line interface: ``politicker-ref validate | run | pipeline | review``."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from .accommodation import confusion_matrix, format_confusion, format_table, review
from .codebook import load_codebook
from .pipeline import execute, load_pipeline
from .providers import ProviderError, ReplayProvider, make_provider
from .run import read_jsonl, read_units, run, select_units


def cmd_validate(args) -> int:
    codebook = load_codebook(args.codebook)
    print(f"{codebook.id} v{codebook.version}: valid")
    print(f"snapshot hash: {codebook.snapshot_hash()}")
    print(f"constructs: {', '.join(codebook.question.constructs)}")
    print(json.dumps(codebook.json_schema(), indent=2))
    return 0


def cmd_run(args) -> int:
    codebook = load_codebook(args.codebook)
    units = read_units(args.units)
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


def cmd_pipeline(args) -> int:
    plan = load_pipeline(args.pipeline)
    documents = read_jsonl(args.documents)
    coder = None
    if plan.codebook is not None and not args.no_code:
        try:
            provider = ReplayProvider(read_jsonl(args.replay)) if args.replay else make_provider(plan.codebook)
        except ProviderError as error:
            print(f"Skipping the coding step: {error}")
        else:
            def coder(codebook, units, out_dir):
                return run(codebook, units, provider, root=out_dir, force=args.force)

    out_dir = execute(plan, documents, root=args.runs, code=coder)
    print(f"Plan {plan.hash()[:12]}: outputs in {out_dir}")
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
    print("Accommodation report\n")
    print(format_table(review(codebook, a, b, model)))
    shared = [u for u in sorted(set(a) & set(b)) if u in model]
    print("\nConfusion matrix: reference human coder against the model\n")
    print(format_confusion(confusion_matrix([a[u] for u in shared], [model[u] for u in shared], list(codebook.question.options))))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="politicker-ref", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Validate a codebook and print its snapshot hash and schema")
    p.add_argument("codebook")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("run", help="Code units with a codebook, one unit per call")
    p.add_argument("codebook")
    p.add_argument("units", help="CSV or JSONL file of text units (needs unit_id and the codebook's state fields)")
    p.add_argument("--runs", default="runs", help="Output root (default: runs)")
    p.add_argument("--replay", help="Recorded outputs.jsonl to replay instead of calling a model")
    p.add_argument("--from-outputs", help="Earlier outputs.jsonl used with --only-codes")
    p.add_argument("--only-codes", help="Comma-separated codes: rerun only units coded this way in --from-outputs")
    p.add_argument("--limit", type=int, help="Code only the first N units (pilot run)")
    p.add_argument("--force", action="store_true", help="Recode units already coded under this snapshot")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("pipeline", help="Run a declarative pipeline: segment, filter and code documents")
    p.add_argument("pipeline", help="Pipeline definition (YAML)")
    p.add_argument("documents", help="JSONL file of documents")
    p.add_argument("--runs", default="runs", help="Output root (default: runs)")
    p.add_argument("--replay", help="Recorded outputs.jsonl to replay instead of calling a model")
    p.add_argument("--no-code", action="store_true", help="Segment and filter only")
    p.add_argument("--force", action="store_true", help="Recode units already coded under this codebook")
    p.set_defaults(func=cmd_pipeline)

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
