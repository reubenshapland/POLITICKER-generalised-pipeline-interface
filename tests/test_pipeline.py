import json
from pathlib import Path

import pytest

from getref.pipeline import (
    AiTermsFilter,
    CongressionalRecordSpeeches,
    HansardContributions,
    Plan,
    PipelineDefinition,
    ai_terms_in,
    execute,
    load_pipeline,
)
from getref.providers import ReplayProvider
from getref.run import read_jsonl, run

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipelines" / "ai-discourse-uk-us.yaml"

US_TEXT = """
[Congressional Record Volume 172, Number 150 (Tuesday, September 22, 2026)]
[Senate]
[Page S4848]
From the Congressional Record Online through the Government Publishing Office [www.gpo.gov]

                        Artificial Intelligence

  Mr. President, this opening speech continues from the previous item and
discusses AI at some length so that it is long enough to keep.
  Mr. KELLY. Mr. President, I want to talk about artificial intelligence
and the risks it poses, and what Congress should do about it now.
  The PRESIDING OFFICER. The Senator from Texas.
  Mr. CRUZ of Texas. Mr. President, thank you.
"""


def us_doc(title="Artificial Intelligence"):
    return {"doc_id": "us-1", "jurisdiction": "US", "chamber": "Senate", "date": "2026-09-22", "title": title,
            "format": "congressional_record_text", "text": US_TEXT, "url": "u"}


def uk_doc(title, texts):
    return {"doc_id": "uk-1", "jurisdiction": "UK", "chamber": "Commons", "date": "2025-01-13", "title": title,
            "format": "hansard_contributions", "url": "u",
            "contributions": [{"speaker": f"Member {i}", "text": t} for i, t in enumerate(texts)]}


LONG = "word " * 30


# Segmentation ---------------------------------------------------------------


def test_congressional_record_is_split_at_speaker_turns():
    segments = CongressionalRecordSpeeches(None).apply(us_doc())
    assert [s["speaker"] for s in segments] == [None, "Mr. KELLY", "The PRESIDING OFFICER", "Mr. CRUZ of Texas"]
    assert segments[0]["text"].startswith("Mr. President, this opening speech")
    assert "Congressional Record" not in segments[0]["text"]
    assert segments[1]["text"].startswith("Mr. President, I want to talk")
    assert "\n" not in segments[1]["text"].strip()  # hard-wrapped lines are joined


def test_segmenters_only_handle_their_own_format():
    assert HansardContributions(None).apply(us_doc()) is None
    assert CongressionalRecordSpeeches(None).apply(uk_doc("T", ["x"])) is None


# AI terms ---------------------------------------------------------------------


@pytest.mark.parametrize("text", ["she said so", "Taiwan", "maintain", "the ai cittadini", "artificial sweetener"])
def test_body_text_non_matches(text):
    assert ai_terms_in(text, title=False) == []


@pytest.mark.parametrize(
    "text, term",
    [("AI", "AI"), ("AI-driven tools", "AI"), ("the AI's role", "AI"), ("Machine-Learning", "machine learning"),
     ("Artificial Intelligence", "artificial intelligence"), ("Generative AI models", "generative AI"),
     ("agentic artificial intelligence", "agentic AI"), ("deep learning", "deep learning")],
)
def test_body_text_matches(text, term):
    assert term in ai_terms_in(text, title=False)


def test_lower_case_ai_matches_in_titles_only():
    assert ai_terms_in("Ai Safety", title=True) == ["AI"]
    assert ai_terms_in("Ai Safety", title=False) == []


# Filter -----------------------------------------------------------------------


def test_titled_section_keeps_every_substantive_speech():
    segments = HansardContributions(None).apply(uk_doc("Artificial Intelligence Opportunities", [LONG, "Order."]))
    kept = AiTermsFilter({}).apply(segments)
    assert len(kept) == 1 and kept[0]["selection"] == "ai_titled_section"


def test_other_sections_keep_only_speeches_mentioning_ai():
    segments = HansardContributions(None).apply(uk_doc("Children's Health", [LONG, LONG + " and AI chatbots"]))
    kept = AiTermsFilter({}).apply(segments)
    assert [k["unit_id"] for k in kept] == ["uk-1#002"] and kept[0]["selection"] == "ai_mention"


def test_long_speeches_are_reduced_to_windows_around_mentions():
    text = "filler " * 1000 + "artificial intelligence " + "filler " * 1000 + "AI " + "filler " * 1000
    segments = HansardContributions(None).apply(uk_doc("Budget", [text]))
    kept = AiTermsFilter({"max_words": 500, "window_words": 50}).apply(segments)[0]
    assert kept["excerpted"] and kept["words"] > 3000
    assert len(kept["text"].split()) <= 500 and "[...]" in kept["text"]
    assert "artificial intelligence" in kept["text"] and " AI " in kept["text"]


# Plans --------------------------------------------------------------------------


def definition(**changes):
    import yaml

    data = yaml.safe_load(PIPELINE.read_text())
    data.update(changes)
    return PipelineDefinition.model_validate(data)


def test_pipeline_loads_and_hashes_its_codebook():
    plan = load_pipeline(PIPELINE)
    assert plan.codebook.id == "institutional-pillars-ai"
    assert plan.canonical()["codebook"] == plan.codebook.canonical()
    assert Plan(definition(version=2), ROOT).hash() != plan.hash()


def test_unknown_strategies_and_bad_order_fail_at_load():
    with pytest.raises(ValueError, match="unknown strategy"):
        Plan(definition(steps=[{"id": "x", "strategy": "segment.pdf"}]), ROOT)
    with pytest.raises(ValueError, match="segment, then filter"):
        Plan(definition(steps=[{"id": "f", "strategy": "filter.ai_terms"},
                               {"id": "s", "strategy": "segment.hansard_contributions"}]), ROOT)


def test_execute_writes_plan_and_units_and_codes_them(tmp_path):
    plan = load_pipeline(PIPELINE)
    docs = [us_doc(), uk_doc("Children's Health", [LONG + " AI"])]
    recorded = []

    def coder(codebook, units, out_dir):
        records = [{"unit_id": u["unit_id"], "snapshot_hash": codebook.snapshot_hash(), "code": "regulative"} for u in units]
        recorded.extend(records)
        return run(codebook, units, ReplayProvider(records), root=out_dir, log=lambda _: None)

    out = execute(plan, docs, root=tmp_path, code=coder, log=lambda _: None)
    assert json.loads((out / "plan.json").read_text())["plan_hash"] == plan.hash()
    units = read_jsonl(out / "units.jsonl")
    assert {u["doc_id"] for u in units} == {"us-1", "uk-1"}
    outputs = read_jsonl(out / plan.codebook.id / plan.codebook.short_hash / "outputs.jsonl")
    assert len(outputs) == len(units) == len(recorded)
