"""Codebooks: loading, validation, schema compilation and snapshot hashing.

A codebook is a declarative definition of one coding task, applied to one text
unit at a time. It names the theory, the question asked of each unit, the
allowed codes with their definitions, the model configuration and the
pre-stated thresholds used in the accommodation review.

Before any run, the codebook is frozen into a canonical snapshot and hashed.
The hash identifies the exact codebook version (definitions, instructions,
model and parameters) that produced each output, so a revised codebook never
overwrites the outputs of an earlier one.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

SNAPSHOT_FORMAT = "getref-codebook/1"

RESERVED_CODES = ("residual", "not_relevant")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelConfig(Strict):
    provider: Literal["openrouter_decision", "openai_compatible"]
    model: str = Field(min_length=1)
    temperature: float = 0.0
    base_url: str | None = None


class Thresholds(Strict):
    reliability: float = Field(0.70, ge=0, le=1, description="Minimum human-human Cohen's kappa")
    agreement: float = Field(0.70, ge=0, le=1, description="Minimum model-human Cohen's kappa")
    residual: float = Field(0.20, ge=0, le=1, description="Maximum agreed residual share")


class Question(Strict):
    field: str = Field(min_length=1, pattern=r"^[a-z_][a-z0-9_]*$")
    instructions: str = Field(min_length=1)
    options: dict[str, str] = Field(min_length=2)

    @model_validator(mode="after")
    def _check_options(self) -> "Question":
        for code in self.options:
            if not code or not code.replace("_", "").isalnum() or code != code.lower():
                raise ValueError(f"Code {code!r} must be lower-case letters, digits and underscores")
        missing = [c for c in RESERVED_CODES if c not in self.options]
        if missing:
            raise ValueError(
                f"Codebooks must define the residual and relevance codes {list(RESERVED_CODES)}; missing {missing}"
            )
        if len(self.constructs) < 1:
            raise ValueError("Codebooks must define at least one construct besides residual and not_relevant")
        return self

    @property
    def constructs(self) -> list[str]:
        return [c for c in self.options if c not in RESERVED_CODES]


class Codebook(Strict):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int = Field(ge=1)
    title: str
    theory: str
    unit: str
    state_fields: list[str] = Field(min_length=1)
    question: Question
    model: ModelConfig
    thresholds: Thresholds = Thresholds()

    def canonical(self) -> dict:
        """The frozen form that is hashed and stored with every run."""
        return {"format": SNAPSHOT_FORMAT, "codebook": self.model_dump(mode="json")}

    def snapshot_hash(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def short_hash(self) -> str:
        return self.snapshot_hash()[:12]

    def output_model(self) -> type[BaseModel]:
        """Compile the codebook into a Pydantic model whose code field is an enum.

        A response that names a code outside the codebook fails validation, so
        format and category errors are separated from substantive coding errors.
        """
        code_enum = Enum(f"{_camel(self.id)}Code", {c.upper(): c for c in self.question.options}, type=str)
        return create_model(
            f"{_camel(self.id)}Output",
            __config__=ConfigDict(extra="forbid"),
            **{self.question.field: (code_enum, ...)},
        )

    def json_schema(self) -> dict:
        """A reference-free JSON Schema for providers with structured output."""
        return {
            "type": "object",
            "properties": {
                self.question.field: {"type": "string", "enum": list(self.question.options)},
            },
            "required": [self.question.field],
            "additionalProperties": False,
        }


def _camel(text: str) -> str:
    return "".join(part.capitalize() for part in text.replace("-", "_").split("_"))


def load_codebook(path: str | Path) -> Codebook:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return Codebook.model_validate(data)
