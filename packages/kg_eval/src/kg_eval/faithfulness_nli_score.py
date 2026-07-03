"""NLI-label агрегатор верности (FaithJudge/HHEM, §23.31/§23.35).

Отличается от ``claim_support`` (совпадение чисел) и ``citation_check``
(существование id): вход — последовательность per-claim NLI-вердиктов против
процитированного evidence, каждый ``{'label': ..., 'weight': ...}`` с меткой
``entail``/``neutral``/``contradict``. Метки в стиле NLI-судей HHEM/FaithJudge
(Vectara, arXiv:2505.04847): ``entail`` — claim следует из evidence,
``neutral`` — не поддержан (галлюцинация), ``contradict`` — противоречит.
Верность = взвешенная доля ``entail``; строгий гейт: любое ``contradict``
делает ответ неверным независимо от порога. Чистый python, детерминизм.

An NLI-label faithfulness aggregator (FaithJudge/HHEM, §23.31/§23.35).
Distinct from ``claim_support`` (number-match) and ``citation_check`` (id
existence): the input is a sequence of per-claim NLI verdicts against the
cited evidence, each ``{'label': ..., 'weight': ...}`` with an
``entail``/``neutral``/``contradict`` label in the style of the HHEM/FaithJudge
NLI judges (Vectara, arXiv:2505.04847). Faithfulness is the weighted share of
``entail``; a strict gate marks any ``contradict`` as unfaithful regardless of
the threshold. Pure python, deterministic — same input yields same output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Допустимые NLI-метки / valid NLI labels.
_LABELS: frozenset[str] = frozenset({"entail", "neutral", "contradict"})


@dataclass(frozen=True)
class FaithfulnessReport:
    """Замороженный итог NLI-агрегации верности (§23.31/§23.35) — RU/EN.

    * ``n`` — число вердиктов / verdict count.
    * ``n_entail`` / ``n_neutral`` / ``n_contradict`` — счётчики по меткам.
    * ``faithfulness`` — взвешенная доля ``entail`` / weighted entail share.
    * ``hallucination_rate`` — взвешенная доля ``neutral+contradict``.
    * ``contradiction_rate`` — взвешенная доля ``contradict``.
    * ``faithful`` — ``faithfulness >= threshold`` и нет противоречий.
    """

    n: int
    n_entail: int
    n_neutral: int
    n_contradict: int
    faithfulness: float
    hallucination_rate: float
    contradiction_rate: float
    faithful: bool

    def as_dict(self) -> dict[str, object]:
        """Return plain ints/bool + floats rounded to 6 (RU: словарь)."""
        return {
            "n": int(self.n),
            "n_entail": int(self.n_entail),
            "n_neutral": int(self.n_neutral),
            "n_contradict": int(self.n_contradict),
            "faithfulness": round(float(self.faithfulness), 6),
            "hallucination_rate": round(float(self.hallucination_rate), 6),
            "contradiction_rate": round(float(self.contradiction_rate), 6),
            "faithful": bool(self.faithful),
        }


def score_faithfulness(
    verdicts: Sequence[Mapping[str, object]],
    *,
    threshold: float = 0.9,
) -> FaithfulnessReport:
    """Агрегировать per-claim NLI-вердикты в отчёт верности (§23.31/§23.35).

    Каждый вердикт — ``{'label': 'entail'|'neutral'|'contradict', 'weight':
    float=1.0}``. ``faithfulness`` = взвешенная доля ``entail``;
    ``hallucination_rate`` = взвешенная доля ``neutral+contradict``;
    ``contradiction_rate`` = взвешенная доля ``contradict``. ``faithful``
    истинно, когда ``faithfulness >= threshold`` и ``contradiction_rate ==
    0.0`` (строгий гейт по противоречиям). Неизвестная метка → ``ValueError``;
    пустой вход → ``ValueError``.

    Aggregates per-claim NLI verdicts into a faithfulness report. Each verdict
    is ``{'label': 'entail'|'neutral'|'contradict', 'weight': float=1.0}``.
    ``faithfulness`` is the weighted ``entail`` share, ``hallucination_rate``
    the weighted ``neutral+contradict`` share and ``contradiction_rate`` the
    weighted ``contradict`` share. ``faithful`` is true when ``faithfulness >=
    threshold`` and ``contradiction_rate == 0.0`` (a strict contradiction
    gate). An unknown label or empty input raises ``ValueError``.
    """
    if not verdicts:
        raise ValueError("verdicts must be non-empty (RU: вход пуст)")

    n_entail = n_neutral = n_contradict = 0
    w_entail = w_neutral = w_contradict = 0.0
    for verdict in verdicts:
        label = verdict["label"]
        if label not in _LABELS:
            raise ValueError(f"unknown NLI label: {label!r} (RU: неизвестная метка)")
        weight = float(verdict.get("weight", 1.0))
        if label == "entail":
            n_entail += 1
            w_entail += weight
        elif label == "neutral":
            n_neutral += 1
            w_neutral += weight
        else:  # contradict
            n_contradict += 1
            w_contradict += weight

    total = w_entail + w_neutral + w_contradict
    faithfulness = 0.0 if total == 0.0 else w_entail / total
    hallucination_rate = 0.0 if total == 0.0 else (w_neutral + w_contradict) / total
    contradiction_rate = 0.0 if total == 0.0 else w_contradict / total
    faithful = faithfulness >= threshold and contradiction_rate == 0.0

    return FaithfulnessReport(
        n=len(verdicts),
        n_entail=n_entail,
        n_neutral=n_neutral,
        n_contradict=n_contradict,
        faithfulness=faithfulness,
        hallucination_rate=hallucination_rate,
        contradiction_rate=contradiction_rate,
        faithful=faithful,
    )
