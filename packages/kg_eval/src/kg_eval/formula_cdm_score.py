"""Formula-recognition CDM-lite — multiset symbol matching (§23.34/§23.31).

Deterministic, hand-checkable scorer for the OmniDocBench *formula* subtask. Where
:mod:`kg_eval.text_edit_distance` grades an OCR/parse string by *ordered* edit
distance (CER/WER), a LaTeX formula is a bag of symbols whose left-to-right order
carries little meaning: ``x^2+1`` and ``1+x^2`` denote the same expression. This
module therefore borrows the spirit of OmniDocBench's CDM («Character Detection
Matching») and scores a predicted formula against gold by **multiset symbol
precision / recall / F1** — сравнение мультимножеств символов, а не правок.

Pipeline:

* :func:`tokenize` strips whitespace and splits a formula into atomic symbols —
  whole LaTeX commands (``\\alpha``), structural chars (``{ } ^ _``), and every
  other non-space character (single digits, letters, operators) on its own;
* :func:`score_formula` compares the two token **multisets**: ``matched`` is the
  multiset-intersection size (respecting multiplicity), ``precision`` normalizes
  it by the prediction token count, ``recall`` by the gold count, and ``f1`` is
  their harmonic mean, bundled into a frozen :class:`FormulaCDM`.

Conventions: two empty formulas are a perfect match (``f1 == 1.0``); exactly one
empty side scores ``0.0``. Pure Python, no I/O.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# A whole LaTeX command (\alpha, \frac, ...) or any single non-whitespace atom.
_TOKEN = re.compile(r"\\[a-zA-Z]+|\S")


def tokenize(s: str) -> tuple[str, ...]:
    """Split a formula into atomic symbol tokens — токенизация (§23.34/§23.31).

    After stripping surrounding whitespace, each match is either a whole LaTeX
    command (backslash + letters, e.g. ``\\alpha``) or a single non-whitespace
    character (``{``, ``}``, ``^``, ``_``, a digit, a letter, an operator).
    Internal whitespace is skipped, so ``' x ^ 2 '`` and ``'x^2'`` tokenize
    identically. Order is preserved but only multiplicity is used downstream.
    """
    return tuple(_TOKEN.findall(s.strip()))


@dataclass(frozen=True)
class FormulaCDM:
    """Frozen verdict of a formula multiset comparison — вердикт формулы (§23.34).

    * ``n_gold`` / ``n_pred`` — token counts of the gold and predicted formulas;
    * ``matched`` — multiset-intersection size (sum of ``min`` per symbol), so a
      symbol shared with lower multiplicity contributes only its overlap;
    * ``precision`` — ``matched / n_pred`` (spurious tokens lower it);
    * ``recall`` — ``matched / n_gold`` (missing tokens lower it);
    * ``f1`` — harmonic mean of ``precision`` and ``recall``.

    Two empty formulas score ``1.0`` across the board; exactly one empty side
    scores ``0.0``.
    """

    n_gold: int
    n_pred: int
    matched: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view; ratios rounded to 6 decimals (§23.34).

        Rounding keeps repeating fractions stable, e.g. an ``f1`` of ``2/3``
        serialises as ``0.666667``.
        """
        return {
            "n_gold": self.n_gold,
            "n_pred": self.n_pred,
            "matched": self.matched,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
        }


def _harmonic(precision: float, recall: float) -> float:
    """Harmonic mean of two ratios — F1 из точности и полноты (§23.34).

    ``2 * p * r / (p + r)``, or ``0.0`` when both are zero (avoids ``0/0``).
    """
    total = precision + recall
    return 0.0 if total == 0 else 2 * precision * recall / total


def score_formula(gold: str, pred: str) -> FormulaCDM:
    """Score ``pred`` against ``gold`` by symbol multisets (§23.34/§23.31).

    Tokenizes both sides, takes ``matched`` as the multiset-intersection size,
    and derives ``precision = matched / n_pred``, ``recall = matched / n_gold``
    and their harmonic ``f1``. Degenerate ratios are pinned so the empty-side
    conventions hold: both empty → ``1.0`` everywhere; exactly one empty →
    ``0.0`` for the facet that would divide by zero, yielding ``f1 == 0.0``.
    """
    gold_tokens = tokenize(gold)
    pred_tokens = tokenize(pred)
    n_gold = len(gold_tokens)
    n_pred = len(pred_tokens)
    matched = sum((Counter(gold_tokens) & Counter(pred_tokens)).values())

    # An empty side has no denominator: it is "perfect" only if the other side is
    # also empty (nothing to recall / nothing spurious), else a total miss.
    precision = matched / n_pred if n_pred else (1.0 if n_gold == 0 else 0.0)
    recall = matched / n_gold if n_gold else (1.0 if n_pred == 0 else 0.0)
    f1 = _harmonic(precision, recall)

    return FormulaCDM(
        n_gold=n_gold,
        n_pred=n_pred,
        matched=matched,
        precision=precision,
        recall=recall,
        f1=f1,
    )
