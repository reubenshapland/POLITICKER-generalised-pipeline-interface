"""Reliability, the agreed residual and the accommodation review.

The review separates measurement failure from theoretical misfit using three
signals, each compared with thresholds stated in the codebook before coding:

=====================  ======================  ==============  ======================================
Human-human            Model-human             Agreed          Interpretation
reliability            agreement               residual
=====================  ======================  ==============  ======================================
Low                    Any                     Any             Ambiguous codebook: revise definitions
High                   Low                     Low             Model limitation: change or tune model
High                   High                    Low             Construct accommodates the phenomenon
High                   Any                     High            Misfit: characterize the agreed residual
=====================  ======================  ==============  ======================================

Reliability is Cohen's kappa. For each construct it is computed on a binary
coding (the construct versus anything else); for the codebook as a whole it is
computed on all codes. The agreed residual is the share of units that both
human coders judge relevant to the phenomenon on which they also agree the
unit fits no construct.

Model performance against the reference human coder is also reported with
precision, recall and F1 for each construct (Sokolova and Lapalme 2009), their
unweighted (macro) averages for the codebook, and a confusion matrix.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from .codebook import Codebook

AMBIGUOUS = "ambiguous codebook"
MODEL_LIMITATION = "model limitation"
ACCOMMODATES = "accommodates"
MISFIT = "misfit"


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Cohen's (1960) kappa for two equal-length sequences of nominal codes.

    Returns None when there are no pairs. Returns 1.0 when both coders use a
    single identical category throughout (observed and expected agreement are
    both 1).
    """
    if len(a) != len(b):
        raise ValueError("Sequences must have equal length")
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def binary(codes: Iterable[str], construct: str) -> list[str]:
    return [construct if c == construct else "other" for c in codes]


def agreed_residual_share(coder_a: Sequence[str], coder_b: Sequence[str]) -> float | None:
    relevant = [(x, y) for x, y in zip(coder_a, coder_b) if x != "not_relevant" and y != "not_relevant"]
    if not relevant:
        return None
    return sum(x == y == "residual" for x, y in relevant) / len(relevant)


def precision_recall_f1(reference: Sequence[str], predicted: Sequence[str], label: str):
    """Precision, recall and F1 of ``predicted`` for one label, against ``reference``.

    Each value is None when undefined (no predictions, or no reference cases, of the label).
    """
    tp = sum(r == p == label for r, p in zip(reference, predicted))
    predicted_n = sum(p == label for p in predicted)
    reference_n = sum(r == label for r in reference)
    precision = tp / predicted_n if predicted_n else None
    recall = tp / reference_n if reference_n else None
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def _macro(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def confusion_matrix(reference: Sequence[str], predicted: Sequence[str], labels: Sequence[str]) -> dict[str, dict[str, int]]:
    """Counts keyed by reference label, then predicted label."""
    matrix = {r: {p: 0 for p in labels} for r in labels}
    for r, p in zip(reference, predicted):
        if r in matrix and p in matrix[r]:
            matrix[r][p] += 1
    return matrix


def format_confusion(matrix: dict[str, dict[str, int]]) -> str:
    labels = list(matrix)
    lines = ["| reference \\ model | " + " | ".join(labels) + " |", "|" + "---|" * (len(labels) + 1)]
    for r in labels:
        lines.append(f"| {r} | " + " | ".join(str(matrix[r][p]) for p in labels) + " |")
    return "\n".join(lines)


def interpret(hh: float | None, mh: float | None, residual: float | None, codebook: Codebook) -> str | None:
    t = codebook.thresholds
    if hh is None:
        return None
    if hh < t.reliability:
        return AMBIGUOUS
    if residual is not None and residual > t.residual:
        return MISFIT
    if mh is None:
        return None
    return ACCOMMODATES if mh >= t.agreement else MODEL_LIMITATION


@dataclass
class Signals:
    scope: str
    units: int
    human_human_kappa: float | None
    model_human_kappa: float | None
    agreed_residual: float | None
    interpretation: str | None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None

    def row(self) -> dict:
        return asdict(self)


def review(
    codebook: Codebook,
    human_a: dict[str, str],
    human_b: dict[str, str],
    model: dict[str, str],
) -> list[Signals]:
    """Compute the three signals for the codebook and for each construct.

    ``human_a``, ``human_b`` and ``model`` map unit_id to code. Only units coded
    by both humans enter the review; the model-human comparison uses units also
    coded by the model, compared with human coder A as reference.
    """
    shared = sorted(set(human_a) & set(human_b))
    a = [human_a[u] for u in shared]
    b = [human_b[u] for u in shared]
    with_model = [u for u in shared if u in model]
    ref = [human_a[u] for u in with_model]
    m = [model[u] for u in with_model]
    residual = agreed_residual_share(a, b)

    hh, mh = cohen_kappa(a, b), cohen_kappa(ref, m)
    construct_rows = []
    for construct in codebook.question.constructs:
        hh_c = cohen_kappa(binary(a, construct), binary(b, construct))
        mh_c = cohen_kappa(binary(ref, construct), binary(m, construct))
        p, r, f = precision_recall_f1(ref, m, construct)
        construct_rows.append(
            Signals(construct, len(shared), hh_c, mh_c, residual, interpret(hh_c, mh_c, residual, codebook), p, r, f)
        )
    overall = Signals(
        "codebook", len(shared), hh, mh, residual, interpret(hh, mh, residual, codebook),
        _macro(x.precision for x in construct_rows), _macro(x.recall for x in construct_rows), _macro(x.f1 for x in construct_rows),
    )
    return [overall, *construct_rows]


def format_table(rows: list[Signals]) -> str:
    def fmt(v):
        return "n/a" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))

    header = ["scope", "units", "human-human kappa", "model-human kappa", "agreed residual", "interpretation",
              "precision", "recall", "F1"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        values = [r.scope, r.units, r.human_human_kappa, r.model_human_kappa, r.agreed_residual, r.interpretation,
                  r.precision, r.recall, r.f1]
        lines.append("| " + " | ".join(fmt(v) for v in values) + " |")
    return "\n".join(lines)
