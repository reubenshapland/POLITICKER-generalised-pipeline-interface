"""Applying a codebook to text units, one unit per model call.

Each run writes to ``runs/<codebook-id>/<snapshot-hash>/``:

- ``codebook.snapshot.json``: the frozen codebook that produced the outputs.
- ``outputs.jsonl``: one record per unit, with the code, the probability of
  every option (for decision models), the served model, token usage and the
  snapshot hash.

Because outputs are keyed by snapshot hash, a revised codebook writes to a new
directory and never overwrites an earlier version. Rerunning the same snapshot
skips units already coded, unless ``force`` is set, so a run can be resumed or
extended to new units. ``select_units`` restricts a run to a subset of units,
such as those an earlier run coded as residual.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .codebook import Codebook
from .providers import Provider, ProviderError

MAX_ATTEMPTS = 3


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_units(path: str | Path) -> list[dict[str, Any]]:
    """Read text units from a CSV file (with a header row) or a JSONL file.

    Every unit needs a ``unit_id`` column plus the fields the codebook lists in
    ``state_fields``; any other columns are kept and ignored.
    """
    if str(path).lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            units = [dict(row) for row in csv.DictReader(handle)]
    else:
        units = read_jsonl(path)
    missing = [i for i, u in enumerate(units, start=1) if not u.get("unit_id")]
    if missing:
        raise ValueError(f"{path}: rows {missing[:5]} have no unit_id")
    return units


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def run_dir(root: str | Path, codebook: Codebook) -> Path:
    return Path(root) / codebook.id / codebook.short_hash


def select_units(
    units: list[dict[str, Any]], outputs: list[dict[str, Any]] | None = None, codes: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Keep units whose recorded code in ``outputs`` is one of ``codes``."""
    if outputs is None or codes is None:
        return units
    wanted = set(codes)
    keep = {o["unit_id"] for o in outputs if o.get("code") in wanted}
    return [u for u in units if u["unit_id"] in keep]


def run(
    codebook: Codebook,
    units: list[dict[str, Any]],
    provider: Provider,
    root: str | Path = "runs",
    force: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> Path:
    out_dir = run_dir(root, codebook)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "codebook.snapshot.json"
    snapshot_path.write_text(
        json.dumps({"snapshot_hash": codebook.snapshot_hash(), **codebook.canonical()}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    outputs_path = out_dir / "outputs.jsonl"
    done: set[str] = set()
    if outputs_path.exists() and not force:
        done = {r["unit_id"] for r in read_jsonl(outputs_path)}
    elif outputs_path.exists():
        outputs_path.unlink()

    todo = [u for u in units if u["unit_id"] not in done]
    log(f"Codebook {codebook.id} v{codebook.version}, snapshot {codebook.short_hash}: {len(todo)} units to code")
    for index, unit in enumerate(todo, start=1):
        coding = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                coding = provider.code(codebook, unit)
                break
            except ProviderError as error:
                log(f"  {unit['unit_id']}: attempt {attempt} failed: {error}")
                if attempt < MAX_ATTEMPTS:
                    sleep(2**attempt)
        if coding is None:
            log(f"  {unit['unit_id']}: gave up after {MAX_ATTEMPTS} attempts; rerun to retry")
            continue
        append_jsonl(
            outputs_path,
            {
                "unit_id": unit["unit_id"],
                "codebook_id": codebook.id,
                "codebook_version": codebook.version,
                "snapshot_hash": codebook.snapshot_hash(),
                "provider": codebook.model.provider,
                "model": codebook.model.model,
                "served_model": coding.served_model,
                "code": coding.code,
                "probabilities": coding.probabilities,
                "usage": coding.usage,
                "raw": coding.raw,
                "coded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        log(f"  [{index}/{len(todo)}] {unit['unit_id']}: {coding.code}")
    return out_dir
