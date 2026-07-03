"""Topic risk-zone classification for the executive dashboard (§24.15).

The executive dashboard (§24.15) surfaces *зоны риска* — topics whose knowledge
base is fragile enough that any answer built on them should be treated with
caution. This module turns a flat list of per-topic aggregates into a ranked
list of :class:`TopicRisk` verdicts, each carrying the concrete *flags* that
tripped and an overall ``risk_level``.

Зоны риска по темам. Каждая тема проверяется по четырём независимым признакам:

- ``low_sources`` — слишком мало источников (``source_count < min_sources``):
  вывод опирается на единичные свидетельства;
- ``contradictory`` — есть противоречия (``contradiction_count > 0``):
  источники расходятся между собой;
- ``no_technoeconomic`` — нет технико-экономических показателей
  (``has_technoeconomic`` is false): нельзя оценить применимость;
- ``stale`` — источники устарели (``latest_year`` старше ``stale_years`` лет
  относительно ``current_year``).

The overall :attr:`TopicRisk.score` is simply the number of flags that tripped,
and :attr:`TopicRisk.risk_level` buckets that score: ``0 -> 'none'``,
``1 -> 'low'``, ``2 -> 'medium'``, ``>= 3 -> 'high'``.

Pure-python and read-only: this module aggregates records handed to it and
never touches the graph, so the Kuzu note (custom node props are not queryable
columns) does not apply here. Callers upstream must read any custom props via
``get_node`` before building the record dicts consumed by
:func:`classify_topics`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# The four risk flags (§24.15), in the canonical order they are emitted.
LOW_SOURCES = "low_sources"
CONTRADICTORY = "contradictory"
NO_TECHNOECONOMIC = "no_technoeconomic"
STALE = "stale"

# All flags in canonical order — used to keep every TopicRisk deterministic.
FLAG_ORDER: tuple[str, ...] = (LOW_SOURCES, CONTRADICTORY, NO_TECHNOECONOMIC, STALE)

# Risk levels (§24.15), from the score buckets below.
NONE = "none"
LOW = "low"
MEDIUM = "medium"
HIGH = "high"


def _risk_level(score: int) -> str:
    """Bucket a flag ``score`` into a risk level (§24.15).

    ``0 -> 'none'``, ``1 -> 'low'``, ``2 -> 'medium'``, ``>= 3 -> 'high'``.
    Уровень риска по числу сработавших признаков.
    """
    if score <= 0:
        return NONE
    if score == 1:
        return LOW
    if score == 2:
        return MEDIUM
    return HIGH


@dataclass(frozen=True)
class TopicRisk:
    """Risk-zone verdict for a single topic (§24.15).

    - ``topic`` — the topic label;
    - ``flags`` — tuple (canonical order) of the tripped risk flags, a subset
      of ``{'low_sources', 'contradictory', 'no_technoeconomic', 'stale'}``;
    - ``risk_level`` — one of ``{'high', 'medium', 'low', 'none'}``;
    - ``score`` — number of flags that tripped (``== len(flags)``).

    Вердикт зоны риска по одной теме.
    """

    topic: str
    flags: tuple[str, ...]
    risk_level: str
    score: int

    def as_dict(self) -> dict[str, object]:
        """JSON-ready mapping of all four fields (§24.15)."""
        return {
            "topic": self.topic,
            "flags": list(self.flags),
            "risk_level": self.risk_level,
            "score": self.score,
        }


def _flags_for(
    record: Mapping[str, object], *, current_year: int, min_sources: int, stale_years: int
) -> tuple[str, ...]:
    """Compute the tripped flags for one ``record`` in canonical order (§24.15).

    Признаки риска для одной темы, в каноническом порядке ``FLAG_ORDER``.
    """
    flags: list[str] = []

    source_count = int(record.get("source_count", 0) or 0)
    if source_count < min_sources:
        flags.append(LOW_SOURCES)

    contradiction_count = int(record.get("contradiction_count", 0) or 0)
    if contradiction_count > 0:
        flags.append(CONTRADICTORY)

    if not bool(record.get("has_technoeconomic", False)):
        flags.append(NO_TECHNOECONOMIC)

    latest_year = record.get("latest_year")
    if latest_year is not None and (current_year - int(latest_year)) > stale_years:
        flags.append(STALE)

    return tuple(flags)


def classify_topics(
    records: Sequence[Mapping[str, object]],
    *,
    current_year: int,
    min_sources: int = 3,
    stale_years: int = 5,
) -> list[TopicRisk]:
    """Classify ``records`` into ranked risk-zone verdicts (§24.15).

    Each record carries ``topic``, ``source_count``, ``contradiction_count``,
    ``has_technoeconomic`` (bool) and ``latest_year``. A flag trips when:
    ``source_count < min_sources`` (``low_sources``), ``contradiction_count > 0``
    (``contradictory``), ``has_technoeconomic`` is false (``no_technoeconomic``),
    or the source is older than ``stale_years`` relative to ``current_year``
    (``stale``). The ``score`` equals the flag count and drives ``risk_level``.

    Returns a list sorted by ``score`` descending, then ``topic`` ascending.
    Классификация тем по зонам риска, отсортированная по убыванию score.
    """
    verdicts: list[TopicRisk] = []
    for record in records:
        flags = _flags_for(
            record, current_year=current_year, min_sources=min_sources, stale_years=stale_years
        )
        score = len(flags)
        verdicts.append(
            TopicRisk(
                topic=str(record.get("topic", "")),
                flags=flags,
                risk_level=_risk_level(score),
                score=score,
            )
        )
    verdicts.sort(key=lambda v: (-v.score, v.topic))
    return verdicts
