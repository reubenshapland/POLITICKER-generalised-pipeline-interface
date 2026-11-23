"""Build the public sample of text units from the UK Parliament Hansard API.

The sample is a small, stratified set of spoken contributions from the House
of Commons and House of Lords that mention artificial intelligence or related
terms. It is used to demonstrate the workflow, not to make substantive claims.

Source: UK Parliament Hansard, reproduced under the Open Parliament Licence
v3.0 (https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).

The query is fixed below. Because the API's ranking can change over time, the
committed ``data/sample_units.jsonl`` is the canonical sample; rerunning this
script documents how it was drawn but may not return identical units.

Usage:
    python scripts/build_sample.py data/sample_units.jsonl
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date

import requests

API = "https://hansard-api.parliament.uk/search/contributions/Spoken.json"
START, END = "2023-01-01", "2025-12-31"
MIN_WORDS, MAX_WORDS = 60, 350

# (search term, house, number of units). The two AI-specific queries supply
# most units. The broader "algorithm" query adds contributions where AI is
# absent or incidental, so the relevance code has work to do.
STRATA = [
    ('"artificial intelligence"', "Commons", 14),
    ('"artificial intelligence"', "Lords", 14),
    ('"machine learning"', "Commons", 3),
    ('"machine learning"', "Lords", 3),
    ("algorithm", "Commons", 3),
    ("algorithm", "Lords", 3),
]
CANDIDATES_PER_STRATUM = 100


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = html.unescape(text).replace("\r\n", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", title.title()) or "Debate"


def fetch(term: str, house: str) -> list[dict]:
    params = {
        "queryParameters.searchTerm": term,
        "queryParameters.house": house,
        "queryParameters.startDate": START,
        "queryParameters.endDate": END,
        "queryParameters.take": CANDIDATES_PER_STRATUM,
    }
    response = requests.get(API, params=params, timeout=60)
    response.raise_for_status()
    return response.json().get("Results", [])


def to_unit(r: dict, term: str) -> dict:
    sitting = r["SittingDate"][:10]
    return {
        "unit_id": f"hansard-{r['ContributionExtId'].lower()}",
        "source": "UK Parliament Hansard",
        "house": r["House"],
        "date": sitting,
        "debate_title": clean(r.get("DebateSection") or ""),
        "section": r.get("Section"),
        "speaker": r.get("AttributedTo") or r.get("MemberName"),
        "text": clean(r["ContributionTextFull"]),
        "url": (
            f"https://hansard.parliament.uk/{r['House']}/{sitting}/debates/"
            f"{r['DebateSectionExtId']}/{slug(r.get('DebateSection') or '')}"
            f"#contribution-{r['ContributionExtId']}"
        ),
        "sample_stratum": f"{term} | {r['House']}",
        "licence": "Open Parliament Licence v3.0",
    }


def main(out_path: str) -> None:
    units: dict[str, dict] = {}
    for term, house, n in STRATA:
        candidates = []
        for r in fetch(term, house):
            unit = to_unit(r, term)
            words = len(unit["text"].split())
            if MIN_WORDS <= words <= MAX_WORDS and unit["unit_id"] not in units:
                candidates.append(unit)
        # Deterministic, date-spread selection: sort by date and id, take evenly spaced items.
        candidates.sort(key=lambda u: (u["date"], u["unit_id"]))
        if len(candidates) < n:
            print(f"Warning: only {len(candidates)} candidates for {term} / {house}", file=sys.stderr)
        step = max(len(candidates) / n, 1) if candidates else 1
        for i in range(min(n, len(candidates))):
            unit = candidates[int(i * step)]
            units[unit["unit_id"]] = unit
    with open(out_path, "w", encoding="utf-8") as handle:
        for unit in sorted(units.values(), key=lambda u: (u["date"], u["unit_id"])):
            handle.write(json.dumps(unit, ensure_ascii=False) + "\n")
    print(f"Wrote {len(units)} units to {out_path} (retrieved {date.today().isoformat()})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/sample_units.jsonl")
