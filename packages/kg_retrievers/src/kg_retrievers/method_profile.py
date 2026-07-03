"""Per-method profile card builder (§24.11).

Assembles the method "profile card" enumerated in §24.11 — *principle*,
*applicability*, *input conditions*, *performance metrics*, *limitations*,
*capex/opex*, *source count* and *confidence* — from a raw method record plus
the list of supporting source ids. No such card assembler exists today; the
retrievers surface only individual method fields, never the consolidated §24.11
view with a source-count-derived confidence band.

Собирает карточку метода из §24.11 (принцип, применимость, входные условия,
метрики, ограничения, capex/opex, число источников, уверенность) из сырого
record и списка идентификаторов источников, выводя полосу уверенности из
количества уникальных источников.

Confidence banding from unique source count:
- ``0`` sources → ``'none'``;
- ``1`` source → ``'low'``;
- ``2``–``3`` sources → ``'medium'``;
- ``>= 4`` sources → ``'high'``.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Record keys whose values become order-preserving, deduplicated tuple fields.
_TUPLE_FIELDS: tuple[str, ...] = (
    "input_conditions",
    "performance_metrics",
    "limitations",
)


def confidence_from_sources(n: int) -> str:
    """Map a unique source count to a §24.11 confidence band.

    ``0`` → ``'none'``, ``1`` → ``'low'``, ``2``–``3`` → ``'medium'`` and any
    count ``>= 4`` → ``'high'``. Negative counts are treated as ``0``.
    """
    if n <= 0:
        return "none"
    if n == 1:
        return "low"
    if n <= 3:
        return "medium"
    return "high"


def _dedupe_preserve_order(values: Iterable[object]) -> tuple[str, ...]:
    """Return string values with duplicates dropped, first-seen order kept."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class MethodProfile:
    """Consolidated §24.11 profile card for a single method.

    - ``method_id`` — identifier of the profiled method;
    - ``principle`` — working principle prose (``None`` if unknown);
    - ``applicability`` — applicability statement (``None`` if unknown);
    - ``input_conditions`` — required input conditions, deduped, order kept;
    - ``performance_metrics`` — reported metrics, deduped, order kept;
    - ``limitations`` — known limitations, deduped, order kept;
    - ``capex`` — capital-expenditure note (``None`` if unknown);
    - ``opex`` — operating-expenditure note (``None`` if unknown);
    - ``source_count`` — number of *unique* supporting source ids;
    - ``confidence`` — band from :func:`confidence_from_sources`.
    """

    method_id: str
    principle: str | None
    applicability: str | None
    input_conditions: tuple[str, ...]
    performance_metrics: tuple[str, ...]
    limitations: tuple[str, ...]
    capex: str | None
    opex: str | None
    source_count: int
    confidence: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping; tuple fields become lists."""
        return {
            "method_id": self.method_id,
            "principle": self.principle,
            "applicability": self.applicability,
            "input_conditions": list(self.input_conditions),
            "performance_metrics": list(self.performance_metrics),
            "limitations": list(self.limitations),
            "capex": self.capex,
            "opex": self.opex,
            "source_count": self.source_count,
            "confidence": self.confidence,
        }


def build_method_profile(record: dict, source_ids: Sequence[str]) -> MethodProfile:
    """Build a §24.11 :class:`MethodProfile` from ``record`` and ``source_ids``.

    Scalar text fields (``principle``, ``applicability``, ``capex``, ``opex``)
    default to ``None`` when absent. The three list fields are deduplicated with
    first-seen order preserved. ``source_ids`` are deduplicated before counting,
    and the count drives the :func:`confidence_from_sources` band.
    """
    method_id = str(record.get("method_id", ""))
    unique_sources = _dedupe_preserve_order(source_ids)
    source_count = len(unique_sources)

    tuples: dict[str, tuple[str, ...]] = {}
    for key in _TUPLE_FIELDS:
        raw = record.get(key) or ()
        tuples[key] = _dedupe_preserve_order(raw)

    def _scalar(key: str) -> str | None:
        value = record.get(key)
        return None if value is None else str(value)

    return MethodProfile(
        method_id=method_id,
        principle=_scalar("principle"),
        applicability=_scalar("applicability"),
        input_conditions=tuples["input_conditions"],
        performance_metrics=tuples["performance_metrics"],
        limitations=tuples["limitations"],
        capex=_scalar("capex"),
        opex=_scalar("opex"),
        source_count=source_count,
        confidence=confidence_from_sources(source_count),
    )
