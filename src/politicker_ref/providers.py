"""Model providers. Each one codes a single text unit against a codebook.

Two live providers are included:

- ``openrouter_decision`` calls a decision model (TypeSafe Jev) through
  OpenRouter's alpha Decisions API. Decision models return one option from a
  predefined answer space with a probability for every option, rather than
  generated text. The codebook's options become the answer space.
- ``openai_compatible`` calls any chat completions endpoint that supports
  JSON Schema structured output: OpenRouter, or a local open-weight model
  served by Ollama or vLLM. The response is validated against the compiled
  codebook schema.

``ReplayProvider`` returns recorded outputs, so results can be reproduced
exactly without an API key or network access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from .codebook import Codebook

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 120


class ProviderError(RuntimeError):
    """A failure that retrying the same request may fix (rate limit, refusal, off-codebook answer)."""


@dataclass
class Coding:
    code: str
    probabilities: dict[str, float] = field(default_factory=dict)
    served_model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class Provider(Protocol):
    def code(self, codebook: Codebook, unit: dict[str, Any]) -> Coding: ...


def state_for(codebook: Codebook, unit: dict[str, Any]) -> dict[str, str]:
    missing = [f for f in codebook.state_fields if f not in unit]
    if missing:
        raise KeyError(f"Unit {unit.get('unit_id')!r} lacks state fields {missing}")
    return {f: str(unit[f]) for f in codebook.state_fields}


class OpenRouterDecisionProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, session: Any = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError("Set OPENROUTER_API_KEY to call the Decisions API, or use --replay")
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL") or OPENROUTER_BASE_URL).rstrip("/")
        self.session = session or requests.Session()

    def code(self, codebook: Codebook, unit: dict[str, Any]) -> Coding:
        question = {
            "type": "choice",
            "instructions": codebook.question.instructions.strip(),
            "criteria": codebook.question.options,
        }
        payload = {
            "model": codebook.model.model,
            "state": state_for(codebook, unit),
            "questions": {codebook.question.field: question},
        }
        # The Decisions API sits beside /v1, at /api/alpha/decisions. It is an alpha endpoint.
        url = f"{self.base_url.removesuffix('/v1')}/alpha/decisions"
        body = _post(self.session, url, payload, self.api_key)

        answer = (body.get("answers") or {}).get(codebook.question.field)
        if not isinstance(answer, dict) or answer.get("type") == "refusal":
            raise ProviderError(f"No answer for {codebook.question.field!r}: {answer}")
        choice = answer.get("choice")
        if choice not in codebook.question.options:
            raise ProviderError(f"Answer {choice!r} is not a code in the codebook")
        probabilities = {
            k: float(v) for k, v in (answer.get("probabilities") or {}).items() if isinstance(v, (int, float))
        }
        codebook.output_model().model_validate({codebook.question.field: choice})
        return Coding(
            code=choice,
            probabilities=probabilities,
            served_model=body.get("model") or codebook.model.model,
            usage=body.get("usage") or {},
            raw=answer,
        )


class OpenAICompatibleProvider:
    """Structured output from a chat completions endpoint (OpenRouter, Ollama, vLLM)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, session: Any = None):
        self.base_url = (base_url or os.environ.get("OPENAI_COMPATIBLE_BASE_URL") or OPENROUTER_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_COMPATIBLE_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or "none"
        self.session = session or requests.Session()

    def code(self, codebook: Codebook, unit: dict[str, Any]) -> Coding:
        state = state_for(codebook, unit)
        options = "\n".join(f"- {code}: {definition}" for code, definition in codebook.question.options.items())
        context = "\n\n".join(f"{name.upper()}:\n{value}" for name, value in state.items())
        prompt = (
            f"{codebook.question.instructions.strip()}\n\nCODES:\n{options}\n\n{context}\n\n"
            f"Answer with JSON containing the field {codebook.question.field!r}."
        )
        payload = {
            "model": codebook.model.model,
            "temperature": codebook.model.temperature,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "coding", "strict": True, "schema": codebook.json_schema()},
            },
        }
        body = _post(self.session, f"{self.base_url}/chat/completions", payload, self.api_key)
        try:
            text = body["choices"][0]["message"]["content"]
            parsed = codebook.output_model().model_validate(json.loads(text))
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(f"Response did not match the codebook schema: {error}") from error
        code = getattr(parsed, codebook.question.field).value
        return Coding(code=code, served_model=body.get("model"), usage=body.get("usage") or {}, raw=text)


class ReplayProvider:
    """Returns recorded codings, checked against the codebook snapshot that produced them."""

    def __init__(self, records: list[dict[str, Any]]):
        self.records = {(r["unit_id"], r["snapshot_hash"]): r for r in records}

    def code(self, codebook: Codebook, unit: dict[str, Any]) -> Coding:
        key = (unit["unit_id"], codebook.snapshot_hash())
        if key not in self.records:
            raise ProviderError(
                f"No recorded output for unit {unit['unit_id']!r} under codebook snapshot {codebook.short_hash}"
            )
        r = self.records[key]
        return Coding(
            code=r["code"],
            probabilities=r.get("probabilities") or {},
            served_model=r.get("served_model"),
            usage=r.get("usage") or {},
            raw=r.get("raw"),
        )


def _post(session: Any, url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = session.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    if response.status_code == 429 or response.status_code >= 500:
        raise ProviderError(f"HTTP {response.status_code} from {url}")
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} from {url}: {response.text[:300]}")
    return response.json()


def make_provider(codebook: Codebook) -> Provider:
    if codebook.model.provider == "openrouter_decision":
        return OpenRouterDecisionProvider(base_url=codebook.model.base_url)
    return OpenAICompatibleProvider(base_url=codebook.model.base_url)
