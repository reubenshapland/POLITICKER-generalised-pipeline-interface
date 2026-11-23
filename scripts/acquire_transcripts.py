"""Acquire a small public corpus of transcripts for the demonstration pipeline.

Two jurisdictions, two kinds of document each:

- **UK Parliament (Hansard API).** Whole debates from the House of Commons and
  House of Lords. Each debate arrives as a list of contributions (speeches)
  with speaker attribution.
- **US Congress (GovInfo).** Items from the Congressional Record, the
  Senate's and House's record of proceedings. Each item arrives as plain
  text, in which speakers are introduced as, for example, "Mr. KELLY."

For each jurisdiction the corpus mixes documents whose title contains
"artificial intelligence" with documents that mention it only in the body.
This lets the pipeline's filter apply both rules: keep every speech in an
AI-titled section, and elsewhere keep only speeches that mention AI.

Acquisition is deliberately separate from the pipeline. It produces documents
in a common format; the pipeline processes one document at a time.

Licences: UK Parliament material under the Open Parliament Licence v3.0. The
Congressional Record is a work of the US Government and is in the public domain.

Usage:
    python scripts/acquire_transcripts.py data/transcripts.jsonl
    (US search uses GovInfo's public DEMO_KEY unless GOVINFO_API_KEY is set.)
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import date

import requests

YEARS = (2023, 2024, 2025)
UK_PER_CELL = 1  # per house, year and title group
US_PER_CELL = 2  # per year and title group
SPEAKER_TURN = re.compile(r"^ {2}(?:(?:Mr|Mrs|Ms|Miss|Madam|Dr)\. [A-Z][A-Za-z'\-]*[A-Z][A-Za-z'\-]*(?: of [A-Z][A-Za-z ]+)?|The [A-Z][A-Z ]+?(?: pro tempore)?(?: \([^)]*\))?)\. ", re.M)

HANSARD = "https://hansard-api.parliament.uk"
GOVINFO_SEARCH = "https://api.govinfo.gov/search"
GOVINFO_HTML = "https://www.govinfo.gov/content/pkg/{package}/html/{granule}.htm"
AI_TITLE = re.compile(r"artificial intelligence|\bAI\b", re.I)

session = requests.Session()
session.headers["User-Agent"] = "getref-research-artifact/0.1 (academic research)"


def get_json(url: str, **params):
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"[ \t]+", " ", html.unescape(text).replace("\r\n", "\n")).strip()


def slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", title.title()) or "Debate"


# UK -------------------------------------------------------------------------


def uk_candidates(house: str, titled: bool, year: int) -> list[tuple[str, str, str]]:
    """Return (debate ext id, date, title) candidates, oldest first."""
    if titled:
        results = get_json(
            f"{HANSARD}/search/Debates.json",
            **{
                "queryParameters.searchTerm": '"artificial intelligence"',
                "queryParameters.house": house,
                "queryParameters.startDate": f"{year}-01-01",
                "queryParameters.endDate": f"{year}-12-31",
                "queryParameters.take": 100,
            },
        )["Results"]
        rows = [(r["DebateSectionExtId"], r["SittingDate"][:10], r["Title"]) for r in results if AI_TITLE.search(r["Title"])]
    else:
        results = get_json(
            f"{HANSARD}/search/contributions/Spoken.json",
            **{
                "queryParameters.searchTerm": '"artificial intelligence"',
                "queryParameters.house": house,
                "queryParameters.startDate": f"{year}-01-01",
                "queryParameters.endDate": f"{year}-12-31",
                "queryParameters.take": 100,
            },
        )["Results"]
        rows = [
            (r["DebateSectionExtId"], r["SittingDate"][:10], clean(r["DebateSection"]))
            for r in results
            if not AI_TITLE.search(r["DebateSection"] or "")
        ]
    unique = {row[0]: row for row in rows}
    return sorted(unique.values(), key=lambda row: (row[1], row[0]))


def uk_document(ext_id: str, house: str) -> dict | None:
    debate = get_json(f"{HANSARD}/debates/debate/{ext_id}.json")
    overview = debate["Overview"]
    contributions = []

    def collect(node):
        for item in node.get("Items") or []:
            if item.get("ItemType") == "Contribution" and item.get("Value"):
                contributions.append(
                    {"speaker": clean(item.get("AttributedTo") or "") or None, "text": clean(item["Value"])}
                )
        for child in node.get("ChildDebates") or []:
            collect(child)

    collect(debate)
    if not contributions:
        return None
    sitting = overview["Date"][:10]
    title = clean(overview["Title"])
    return {
        "doc_id": f"uk-{ext_id.lower()}",
        "jurisdiction": "UK",
        "chamber": house,
        "date": sitting,
        "title": title,
        "setting": overview.get("Location"),
        "format": "hansard_contributions",
        "contributions": contributions,
        "url": f"https://hansard.parliament.uk/{house}/{sitting}/debates/{ext_id}/{slug(title)}",
        "licence": "Open Parliament Licence v3.0",
    }


# US -------------------------------------------------------------------------


def us_candidates(titled: bool, year: int) -> list[dict]:
    clause = 'title:("artificial intelligence")' if titled else '"artificial intelligence" NOT title:("artificial intelligence")'
    body = {
        "query": f"collection:CREC AND {clause} AND publishdate:range({year}-01-01,{year}-12-31)",
        "pageSize": 100,
        "offsetMark": "*",
        "sorts": [{"field": "publishdate", "sortOrder": "ASC"}],
    }
    key = os.environ.get("GOVINFO_API_KEY", "DEMO_KEY")
    response = session.post(f"{GOVINFO_SEARCH}?api_key={key}", json=body, timeout=60)
    response.raise_for_status()
    results = response.json().get("results", [])
    return [r for r in results if r.get("granuleId") and bool(AI_TITLE.search(r.get("title", ""))) == titled]


def us_document(result: dict) -> dict | None:
    package, granule = result["packageId"], result["granuleId"]
    url = GOVINFO_HTML.format(package=package, granule=granule)
    response = session.get(url, timeout=60)
    if response.status_code != 200:
        return None
    match = re.search(r"<pre>(.*)</pre>", response.text, re.S)
    # Keep line structure (speaker turns start lines), drop page markers.
    text = re.sub(r"\[\[Page [A-Z]?\d+\]\]", "", html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))) if match else ""
    if not text.strip() or not SPEAKER_TURN.search(text):
        return None  # lists, agendas and digests have no speeches
    chamber = "Senate" if "-PgS" in granule else "House" if "-PgH" in granule else "Extensions of Remarks"
    return {
        "doc_id": f"us-{granule.lower()}",
        "jurisdiction": "US",
        "chamber": chamber,
        "date": result.get("dateIssued"),
        "title": clean(result.get("title", "")),
        "setting": chamber,
        "format": "congressional_record_text",
        "text": text,
        "url": url,
        "licence": "Public domain (US Government work)",
    }


def evenly(items: list, n: int) -> list:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main(out_path: str) -> None:
    documents = []
    for year in YEARS:
        for house in ("Commons", "Lords"):
            for titled in (True, False):
                picked = 0
                for ext_id, _, _ in evenly(uk_candidates(house, titled, year), UK_PER_CELL * 3):
                    if picked == UK_PER_CELL:
                        break
                    doc = uk_document(ext_id, house)
                    if doc:
                        documents.append(doc)
                        picked += 1
                    time.sleep(0.5)
                print(f"UK {house} {year}, {'AI-titled' if titled else 'AI in body only'}: {picked}")
        for titled in (True, False):
            picked = 0
            for result in evenly(us_candidates(titled, year), US_PER_CELL * 8):
                if picked == US_PER_CELL:
                    break
                doc = us_document(result)
                if doc:
                    documents.append(doc)
                    picked += 1
                time.sleep(0.5)
            print(f"US {year}, {'AI-titled' if titled else 'AI in body only'}: {picked}")
    with open(out_path, "w", encoding="utf-8") as handle:
        for doc in sorted(documents, key=lambda d: (d["jurisdiction"], d["date"], d["doc_id"])):
            handle.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"Wrote {len(documents)} documents to {out_path} (retrieved {date.today().isoformat()})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/transcripts.jsonl")
