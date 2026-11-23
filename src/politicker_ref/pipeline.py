"""A miniature declarative pipeline: segment, filter and code one document at a time.

A pipeline definition (YAML) lists steps. Each step names a registered strategy
and its configuration. The definition contains no code. It is validated when
loaded, then frozen, together with the codebook it uses, into a plan that is
identified by a content hash. Outputs are written under that hash, so editing
the definition or the codebook never overwrites earlier results.

Each document passes through the steps on its own:

1. ``segment.*`` splits the transcript into speeches.
2. ``filter.ai_terms`` keeps the speeches relevant to AI.
3. ``code.codebook`` codes each kept speech against a codebook, one speech
   per model call (see ``politicker_ref.run``).

This mirrors, in small, the declarative pipeline definitions of the full
infrastructure (``docs/declarative-definitions.md``). It omits that
runtime's orchestration, storage and capability catalogue.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .codebook import Codebook, load_codebook

PLAN_FORMAT = "politicker-pipeline/1"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Strategies -----------------------------------------------------------------

STRATEGIES: dict[str, type["Strategy"]] = {}


def register(cls):
    STRATEGIES[cls.name] = cls
    return cls


class Strategy:
    name: str
    kind: Literal["segment", "filter", "code"]
    version = "1"

    class Config(Strict):
        pass

    def __init__(self, config: dict[str, Any] | None):
        self.config = self.Config.model_validate(config or {})


def _paragraphs(text: str) -> str:
    """Join hard-wrapped lines into paragraphs and normalise spacing."""
    paragraphs = re.split(r"\n\s*\n|\n {2}(?=\S)", text)
    return "\n\n".join(re.sub(r"\s+", " ", p).strip() for p in paragraphs if p.strip())


def _base(doc: dict[str, Any], index: int, speaker: str | None, text: str) -> dict[str, Any]:
    return {
        "unit_id": f"{doc['doc_id']}#{index:03d}",
        "doc_id": doc["doc_id"],
        "jurisdiction": doc["jurisdiction"],
        "chamber": doc["chamber"],
        "date": doc["date"],
        "debate_title": doc["title"],
        "speaker": speaker,
        "text": text,
        "url": doc["url"],
    }


@register
class HansardContributions(Strategy):
    """UK Hansard: each contribution is already one speech with a speaker."""

    name = "segment.hansard_contributions"
    kind = "segment"

    def apply(self, doc):
        if doc.get("format") != "hansard_contributions":
            return None
        return [_base(doc, i, c.get("speaker"), c["text"]) for i, c in enumerate(doc["contributions"], start=1)]


SPEAKER_TURN = re.compile(
    r"^ {2}((?:(?:Mr|Mrs|Ms|Miss|Madam|Dr)\. [A-Z][A-Za-z'\-]*[A-Z][A-Za-z'\-]*(?: of [A-Z][A-Za-z ]+)?)"
    r"|(?:President|Prime Minister|Chairman|Chairwoman|Senator) [A-Z][A-Z' \-]+"
    r"|The [A-Z][A-Z ]+?(?: pro tempore)?(?: \([^)]*\))?)\. ",
    re.M,
)
HEADER_LINE = re.compile(r"^(?:\[.*\]|From the Congressional Record.*| {8,}\S.*)$")


@register
class CongressionalRecordSpeeches(Strategy):
    """US Congressional Record: split plain text at speaker turns such as "  Mr. KELLY. "."""

    name = "segment.congressional_record"
    kind = "segment"

    def apply(self, doc):
        if doc.get("format") != "congressional_record_text":
            return None
        text = doc["text"]
        turns = list(SPEAKER_TURN.finditer(text))
        segments = []
        # An item can open mid-speech, its speaker introduced in the previous
        # item. Keep that opening text, without the record's header lines and
        # centred title, as a speech by an unidentified speaker.
        opening = text[: turns[0].start()] if turns else text
        opening = "\n".join(line for line in opening.splitlines() if not HEADER_LINE.match(line))
        if _paragraphs(opening):
            segments.append(_base(doc, 1, None, _paragraphs(opening)))
        for i, match in enumerate(turns):
            end = turns[i + 1].start() if i + 1 < len(turns) else len(text)
            body = _paragraphs(text[match.end() : end])
            if body:
                segments.append(_base(doc, len(segments) + 1, match.group(1), body))
        return segments


# Words match in any case. The acronym "AI" matches only in upper case in body
# text, where lower-case "ai" can be an ordinary word in other languages; in
# titles every pattern is case-insensitive.
AI_PATTERNS = {
    "artificial intelligence": r"(?i:artificial[\s-]+intelligences?)",
    "AI": r"AI(?:['’]?s)?",
    "machine learning": r"(?i:machine[\s-]+learning)",
    "deep learning": r"(?i:deep[\s-]+learning)",
    "generative AI": r"(?i:generative)[\s-]+(?:AI|(?i:artificial[\s-]+intelligence))",
    "agentic AI": r"(?i:agentic)[\s-]+(?:AI|(?i:artificial[\s-]+intelligence))",
}


def ai_terms_in(text: str, title: bool) -> list[str]:
    """Matched AI terms as whole words ("AI-driven" counts; "said" and "Taiwan" do not)."""
    flags = re.I if title else 0
    return [term for term, pattern in AI_PATTERNS.items() if re.search(rf"(?<!\w){pattern}(?!\w)", text, flags)]


def _windows(text: str, words: int, max_words: int) -> tuple[str, bool]:
    """Merge windows of ``words`` either side of each AI mention; cap at ``max_words``."""
    tokens = text.split()
    hits = [i for i, t in enumerate(tokens) if ai_terms_in(" ".join(tokens[max(0, i - 1) : i + 2]), title=False)]
    if not hits:
        return " ".join(tokens[:max_words]), True
    spans: list[list[int]] = []
    for i in hits:
        lo, hi = max(0, i - words), min(len(tokens), i + words + 1)
        if spans and lo <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    excerpt = " [...] ".join(" ".join(tokens[lo:hi]) for lo, hi in spans)
    return " ".join(excerpt.split()[:max_words]), True


@register
class AiTermsFilter(Strategy):
    """Keep speeches relevant to AI.

    Section rule: if the document's title contains an AI term, keep every
    speech in it. Mention rule: otherwise keep only speeches whose text
    contains an AI term. Speeches shorter than ``min_words`` are dropped as
    procedural. Speeches longer than ``max_words`` are reduced to windows of
    ``window_words`` either side of each mention.
    """

    name = "filter.ai_terms"
    kind = "filter"

    class Config(Strict):
        min_words: int = Field(20, ge=0)
        max_words: int = Field(1500, ge=50)
        window_words: int = Field(150, ge=10)

    def apply(self, segments):
        kept = []
        for seg in segments:
            words = len(seg["text"].split())
            if words < self.config.min_words:
                continue
            title_terms = ai_terms_in(seg["debate_title"], title=True)
            body_terms = ai_terms_in(seg["text"], title=False)
            if not title_terms and not body_terms:
                continue
            seg = {
                **seg,
                "selection": "ai_titled_section" if title_terms else "ai_mention",
                "matched_terms": sorted(set(title_terms) | set(body_terms)),
                "words": words,
                "excerpted": False,
            }
            if words > self.config.max_words:
                seg["text"], seg["excerpted"] = _windows(seg["text"], self.config.window_words, self.config.max_words)
            kept.append(seg)
        return kept


@register
class CodebookStep(Strategy):
    """Code each kept speech against a codebook, one speech per model call."""

    name = "code.codebook"
    kind = "code"

    class Config(Strict):
        codebook: str


# Definitions and plans ------------------------------------------------------


class Step(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    strategy: str
    config: dict[str, Any] = {}


class PipelineDefinition(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int = Field(ge=1)
    description: str
    unit: str
    steps: list[Step] = Field(min_length=1)


class Plan:
    """A validated, frozen pipeline: definition + strategy versions + codebook snapshot."""

    def __init__(self, definition: PipelineDefinition, base_dir: Path):
        self.definition = definition
        self.segmenters, self.filters, self.codebook = [], [], None
        seen_kinds = []
        for step in definition.steps:
            cls = STRATEGIES.get(step.strategy)
            if cls is None:
                raise ValueError(f"Step {step.id!r}: unknown strategy {step.strategy!r}; known: {sorted(STRATEGIES)}")
            instance = cls(step.config)
            seen_kinds.append(cls.kind)
            if cls.kind == "segment":
                self.segmenters.append(instance)
            elif cls.kind == "filter":
                self.filters.append(instance)
            else:
                if self.codebook is not None:
                    raise ValueError("A pipeline may have at most one code step")
                self.codebook = load_codebook(base_dir / instance.config.codebook)
        order = {"segment": 0, "filter": 1, "code": 2}
        if seen_kinds != sorted(seen_kinds, key=order.get) or "segment" not in seen_kinds:
            raise ValueError("Steps must run segment, then filter, then code, and include a segment step")

    def canonical(self) -> dict:
        return {
            "format": PLAN_FORMAT,
            "pipeline": self.definition.model_dump(mode="json"),
            "strategy_versions": {s.strategy: STRATEGIES[s.strategy].version for s in self.definition.steps},
            "codebook": self.codebook.canonical() if self.codebook else None,
        }

    def hash(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def units_for(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        segments = None
        for segmenter in self.segmenters:
            segments = segmenter.apply(doc)
            if segments is not None:
                break
        if segments is None:
            raise ValueError(f"No segment step handles document {doc['doc_id']!r} (format {doc.get('format')!r})")
        for flt in self.filters:
            segments = flt.apply(segments)
        return segments


def load_pipeline(path: str | Path) -> Plan:
    path = Path(path)
    with open(path, encoding="utf-8") as handle:
        definition = PipelineDefinition.model_validate(yaml.safe_load(handle))
    return Plan(definition, base_dir=path.resolve().parent.parent)


def execute(
    plan: Plan,
    documents: list[dict[str, Any]],
    root: str | Path = "runs",
    code: Callable[[Codebook, list[dict[str, Any]], Path], Path] | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    out_dir = Path(root) / "pipelines" / plan.definition.id / plan.hash()[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(
        json.dumps({"plan_hash": plan.hash(), **plan.canonical()}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    units = []
    for doc in documents:
        doc_units = plan.units_for(doc)
        log(f"{doc['doc_id']}: kept {len(doc_units)} speeches")
        units.extend(doc_units)
    with open(out_dir / "units.jsonl", "w", encoding="utf-8") as handle:
        for unit in units:
            handle.write(json.dumps(unit, ensure_ascii=False, sort_keys=True) + "\n")
    log(f"{len(units)} units from {len(documents)} documents written to {out_dir / 'units.jsonl'}")
    if plan.codebook is not None and code is not None:
        code(plan.codebook, units, out_dir)
    return out_dir
