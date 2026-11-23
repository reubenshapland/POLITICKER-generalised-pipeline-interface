import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from politicker_ref.accommodation import (
    ACCOMMODATES,
    AMBIGUOUS,
    MISFIT,
    MODEL_LIMITATION,
    agreed_residual_share,
    cohen_kappa,
    interpret,
    review,
)
from politicker_ref.codebook import Codebook, load_codebook
from politicker_ref.providers import (
    OpenAICompatibleProvider,
    OpenRouterDecisionProvider,
    ProviderError,
    ReplayProvider,
)
from politicker_ref.run import read_jsonl, run, select_units

ROOT = Path(__file__).resolve().parents[1]
CODEBOOK = ROOT / "codebooks" / "institutional-pillars-ai.yaml"
UNIT = {"unit_id": "u1", "debate_title": "AI Regulation", "text": "We need a statutory regulator for AI."}


@pytest.fixture
def codebook() -> Codebook:
    return load_codebook(CODEBOOK)


def edited(codebook: Codebook, **changes) -> Codebook:
    data = codebook.model_dump(mode="json")
    data.update(changes)
    return Codebook.model_validate(data)


# Codebooks -----------------------------------------------------------------


def test_example_codebook_is_valid(codebook):
    assert codebook.question.constructs == ["regulative", "normative", "cultural_cognitive"]


def test_snapshot_hash_is_stable_and_changes_with_any_edit(codebook):
    assert codebook.snapshot_hash() == load_codebook(CODEBOOK).snapshot_hash()
    assert edited(codebook, version=2).snapshot_hash() != codebook.snapshot_hash()
    model = {**codebook.model.model_dump(), "model": "typesafe/jev-9"}
    assert edited(codebook, model=model).snapshot_hash() != codebook.snapshot_hash()


def test_output_model_rejects_codes_outside_the_codebook(codebook):
    model = codebook.output_model()
    assert model.model_validate({"pillar": "normative"})
    with pytest.raises(ValidationError):
        model.model_validate({"pillar": "economic"})
    with pytest.raises(ValidationError):
        model.model_validate({"pillar": "normative", "extra": 1})


def test_codebooks_must_define_residual_and_relevance_codes(codebook):
    data = codebook.model_dump(mode="json")
    del data["question"]["options"]["residual"]
    with pytest.raises(ValidationError, match="residual"):
        Codebook.model_validate(data)


def test_unknown_fields_are_rejected(codebook):
    data = codebook.model_dump(mode="json")
    data["concurrency"] = 8
    with pytest.raises(ValidationError):
        Codebook.model_validate(data)


# Providers -----------------------------------------------------------------


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json))
        return self.responses.pop(0)


def test_decision_provider_sends_codebook_as_answer_space(codebook):
    body = {
        "model": "typesafe/jev-1.14-20261101",
        "answers": {"pillar": {"type": "choice", "choice": "regulative", "probabilities": {"regulative": 0.9, "normative": 0.1}}},
        "usage": {"input_tokens": 50, "output_tokens": 1},
    }
    session = FakeSession(FakeResponse(200, body))
    coding = OpenRouterDecisionProvider(api_key="k", session=session).code(codebook, UNIT)
    url, payload = session.calls[0]
    assert url == "https://openrouter.ai/api/alpha/decisions"
    assert payload["questions"]["pillar"]["criteria"] == codebook.question.options
    assert payload["state"] == {"debate_title": "AI Regulation", "text": UNIT["text"]}
    assert coding.code == "regulative" and coding.probabilities["regulative"] == 0.9
    assert coding.served_model == "typesafe/jev-1.14-20261101"


@pytest.mark.parametrize(
    "answer",
    [{"type": "refusal"}, {"type": "choice", "choice": "economic"}, None],
)
def test_decision_provider_treats_bad_answers_as_retryable(codebook, answer):
    session = FakeSession(FakeResponse(200, {"answers": {"pillar": answer} if answer else {}}))
    with pytest.raises(ProviderError):
        OpenRouterDecisionProvider(api_key="k", session=session).code(codebook, UNIT)


def test_rate_limits_are_retryable(codebook):
    session = FakeSession(FakeResponse(429, {}))
    with pytest.raises(ProviderError):
        OpenRouterDecisionProvider(api_key="k", session=session).code(codebook, UNIT)


def test_openai_compatible_provider_validates_structured_output(codebook):
    ok = {"model": "m", "choices": [{"message": {"content": '{"pillar": "normative"}'}}]}
    bad = {"model": "m", "choices": [{"message": {"content": '{"pillar": "economic"}'}}]}
    session = FakeSession(FakeResponse(200, ok), FakeResponse(200, bad))
    provider = OpenAICompatibleProvider(api_key="k", base_url="http://localhost:11434/v1", session=session)
    assert provider.code(codebook, UNIT).code == "normative"
    schema = session.calls[0][1]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["pillar"]["enum"] == list(codebook.question.options)
    with pytest.raises(ProviderError):
        provider.code(codebook, UNIT)


def test_replay_refuses_outputs_from_another_codebook_version(codebook):
    records = [{"unit_id": "u1", "snapshot_hash": codebook.snapshot_hash(), "code": "normative"}]
    assert ReplayProvider(records).code(codebook, UNIT).code == "normative"
    with pytest.raises(ProviderError):
        ReplayProvider(records).code(edited(codebook, version=2), UNIT)


# Runs ----------------------------------------------------------------------


class ScriptedProvider:
    def __init__(self, codes, failures=0):
        self.codes, self.failures, self.calls = codes, failures, 0

    def code(self, codebook, unit):
        from politicker_ref.providers import Coding

        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ProviderError("transient")
        return Coding(code=self.codes[unit["unit_id"]])


def units(n=3):
    return [{"unit_id": f"u{i}", "debate_title": "T", "text": "x"} for i in range(1, n + 1)]


def test_run_writes_snapshot_and_resumes_without_recoding(codebook, tmp_path):
    provider = ScriptedProvider({"u1": "regulative", "u2": "residual", "u3": "not_relevant"})
    out = run(codebook, units(2), provider, root=tmp_path, log=lambda _: None)
    assert out == tmp_path / codebook.id / codebook.short_hash
    snapshot = json.loads((out / "codebook.snapshot.json").read_text())
    assert snapshot["snapshot_hash"] == codebook.snapshot_hash()
    run(codebook, units(3), provider, root=tmp_path, log=lambda _: None)
    assert provider.calls == 3
    assert [r["unit_id"] for r in read_jsonl(out / "outputs.jsonl")] == ["u1", "u2", "u3"]


def test_revised_codebook_writes_to_a_new_directory(codebook, tmp_path):
    provider = ScriptedProvider({"u1": "regulative"})
    first = run(codebook, units(1), provider, root=tmp_path, log=lambda _: None)
    second = run(edited(codebook, version=2), units(1), provider, root=tmp_path, log=lambda _: None)
    assert first != second and (first / "outputs.jsonl").exists() and (second / "outputs.jsonl").exists()


def test_run_retries_transient_failures(codebook, tmp_path):
    provider = ScriptedProvider({"u1": "normative"}, failures=2)
    out = run(codebook, units(1), provider, root=tmp_path, sleep=lambda _: None, log=lambda _: None)
    assert read_jsonl(out / "outputs.jsonl")[0]["code"] == "normative"


def test_select_units_reruns_only_chosen_codes():
    outputs = [{"unit_id": "u1", "code": "residual"}, {"unit_id": "u2", "code": "normative"}]
    assert [u["unit_id"] for u in select_units(units(3), outputs, ["residual"])] == ["u1"]


# Accommodation review ------------------------------------------------------


def test_cohen_kappa_matches_a_worked_example():
    # 50 items: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po=0.7, pe=0.5, kappa=0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)
    assert cohen_kappa(["y", "y"], ["y", "y"]) == 1.0
    assert cohen_kappa([], []) is None


def test_agreed_residual_counts_only_units_both_coders_find_relevant():
    a = ["residual", "residual", "normative", "not_relevant"]
    b = ["residual", "normative", "normative", "residual"]
    assert agreed_residual_share(a, b) == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "hh, mh, residual, expected",
    [
        (0.5, 0.9, 0.0, AMBIGUOUS),
        (0.9, 0.5, 0.1, MODEL_LIMITATION),
        (0.9, 0.9, 0.1, ACCOMMODATES),
        (0.9, 0.5, 0.4, MISFIT),
        (0.9, 0.9, 0.4, MISFIT),
    ],
)
def test_interpretation_follows_table_1(codebook, hh, mh, residual, expected):
    assert interpret(hh, mh, residual, codebook) == expected


def test_review_reports_codebook_and_each_construct(codebook):
    a = {"u1": "regulative", "u2": "normative", "u3": "residual", "u4": "not_relevant"}
    rows = review(codebook, a, dict(a), dict(a))
    assert [r.scope for r in rows] == ["codebook", "regulative", "normative", "cultural_cognitive"]
    assert rows[0].human_human_kappa == 1.0 and rows[0].interpretation == MISFIT  # 1 of 3 relevant is residual


def test_precision_recall_f1_and_confusion_matrix():
    from politicker_ref.accommodation import confusion_matrix, precision_recall_f1

    ref = ["regulative", "regulative", "normative", "residual"]
    pred = ["regulative", "normative", "normative", "regulative"]
    p, r, f = precision_recall_f1(ref, pred, "regulative")
    assert (p, r) == (0.5, 0.5) and f == pytest.approx(0.5)
    assert precision_recall_f1(ref, pred, "cultural_cognitive") == (None, None, None)
    matrix = confusion_matrix(ref, pred, ["regulative", "normative", "residual"])
    assert matrix["regulative"] == {"regulative": 1, "normative": 1, "residual": 0}
    assert matrix["residual"]["regulative"] == 1


def test_units_can_be_read_from_csv(tmp_path):
    from politicker_ref.run import read_units

    path = tmp_path / "units.csv"
    path.write_text("unit_id,debate_title,text\nu1,AI,We need a regulator.\n", encoding="utf-8")
    assert read_units(path) == [{"unit_id": "u1", "debate_title": "AI", "text": "We need a regulator."}]
    bad = tmp_path / "bad.csv"
    bad.write_text("debate_title,text\nAI,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unit_id"):
        read_units(bad)
