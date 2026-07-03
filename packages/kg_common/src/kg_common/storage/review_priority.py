"""Review-task priority + SLA aging (§16.4 приоритизация задач ревью).

Pure functions that score how urgently a *задача ревью* (review task) needs a
curator, and how long it has been waiting. No store, no I/O, no ``datetime.now``
inside the logic — the caller passes the current instant as an ISO-8601 string,
so results are fully deterministic and hand-checkable (детерминированность).

The task-type / ``kind`` vocabulary is owned by
:mod:`kg_common.storage.review_queue` and the extractor router
(:mod:`kg_extractors.review_routing`): ``low_confidence`` /
``confidence_review`` / ``flag_review`` / ``schema_change`` plus the escalation
reasons ``conflicting`` / ``out_of_range`` / ``missing_unit`` / ``low_ocr``.
This module reads that vocabulary; it never edits the queue.

Priority formula (приоритет, целое 1..100 — чем выше, тем срочнее)
------------------------------------------------------------------
The score sums four independent signals, then clamps to ``[1, 100]``:

* **confidence** (уверенность) — the dominant driver: LOWER confidence yields a
  HIGHER priority (``(1 - confidence) * CONF_WEIGHT``), so the shakiest facts
  sort to the top;
* **task_type** (тип задачи) — a *critical* kind (e.g. ``critical_numeric_value``
  or ``conflicting``) adds a fixed ``CRITICAL_BOOST`` — hard data-integrity
  problems outrank a merely under-confident fact;
* **evidence_count** (число свидетельств) — FEWER supporting evidence pieces
  yield a HIGHER priority (a thinly-supported claim is riskier), decaying to 0
  once enough evidence has accumulated;
* **entity_degree** (степень связности) — a HIGHER graph degree yields a HIGHER
  priority: an error on a well-connected entity poisons more of the graph, so it
  matters more.

SLA aging (старение по SLA)
---------------------------
:func:`age_hours` returns the wall-clock hours between two ISO stamps and
:func:`is_overdue` reports whether a task has aged past its SLA. Naive stamps are
read as UTC so a naive and a ``+00:00`` stamp compare correctly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

# -- critical task kinds (критичные виды задач, §16.4) --------------------
#: Kinds whose data-integrity impact adds :data:`CRITICAL_BOOST` to priority.
#: ``conflicting`` / ``out_of_range`` come from the router (§6.15);
#: ``critical_numeric_value`` marks a load-bearing numeric fact (§7).
CRITICAL_TASK_TYPES: frozenset[str] = frozenset(
    {"critical_numeric_value", "conflicting", "out_of_range"}
)

# -- priority bounds + signal weights (веса сигналов, §16.4) --------------
PRIORITY_MIN = 1  # никогда не ниже 1 (даже идеальный факт остаётся в шкале)
PRIORITY_MAX = 100  # верхняя граница шкалы приоритета

CONF_WEIGHT = 60.0  # вклад (1 - confidence): 0.0 -> 60, 1.0 -> 0
CRITICAL_BOOST = 20.0  # надбавка за критичный тип задачи

EVIDENCE_MAX = 10.0  # максимум вклада при нуле свидетельств
EVIDENCE_STEP = 2.0  # снижение вклада за каждое свидетельство (до нуля)

DEGREE_MAX = 10.0  # насыщение вклада степени связности
DEGREE_STEP = 1.0  # рост вклада за единицу степени (до насыщения)


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into ``[lo, hi]`` (ограничение диапазоном)."""
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class PriorityInputs:
    """Signals feeding :func:`compute_priority` — входы приоритизации (§16.4).

    Fields
    ------
    confidence:
        Extraction confidence in ``[0, 1]`` (уверенность); lower => more urgent.
        Values outside the range are clamped.
    task_type:
        The task ``kind`` (вид задачи); membership in :data:`CRITICAL_TASK_TYPES`
        adds :data:`CRITICAL_BOOST`.
    evidence_count:
        Number of supporting evidence pieces (число свидетельств); fewer => more
        urgent. Negatives are treated as ``0``.
    entity_degree:
        Graph degree of the target entity (степень связности); higher => more
        urgent. Negatives are treated as ``0``.
    """

    confidence: float
    task_type: str
    evidence_count: int
    entity_degree: int

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (all fields, JSON-friendly)."""
        return asdict(self)


def compute_priority(inp: PriorityInputs) -> int:
    """Score a review task's urgency as an int in ``[1, 100]`` (§16.4).

    Higher is more urgent. LOWER confidence, a critical ``task_type``, FEWER
    evidence pieces and a HIGHER ``entity_degree`` all push the score up. The raw
    sum is bounded to ``[PRIORITY_MIN, PRIORITY_MAX]`` — determined solely by the
    inputs (pure / детерминированная функция).
    """
    confidence = _clamp(inp.confidence, 0.0, 1.0)
    evidence = max(0, inp.evidence_count)
    degree = max(0, inp.entity_degree)

    conf_component = (1.0 - confidence) * CONF_WEIGHT
    critical_component = CRITICAL_BOOST if inp.task_type in CRITICAL_TASK_TYPES else 0.0
    evidence_component = max(0.0, EVIDENCE_MAX - evidence * EVIDENCE_STEP)
    degree_component = min(DEGREE_MAX, degree * DEGREE_STEP)

    raw = conf_component + critical_component + evidence_component + degree_component
    return int(_clamp(round(raw), PRIORITY_MIN, PRIORITY_MAX))


def _parse_iso(stamp: str) -> datetime:
    """Parse an ISO-8601 ``stamp`` as a UTC-aware datetime (naive read as UTC)."""
    dt = datetime.fromisoformat(stamp)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def age_hours(created_at_iso: str, now_iso: str) -> float:
    """Wall-clock hours between ``created_at_iso`` and ``now_iso`` (возраст, §16.4).

    Positive when ``now_iso`` is after ``created_at_iso``. Mixed naive / offset
    stamps are compared as UTC.
    """
    delta = _parse_iso(now_iso) - _parse_iso(created_at_iso)
    return delta.total_seconds() / 3600.0


def is_overdue(created_at_iso: str, now_iso: str, sla_hours: float) -> bool:
    """Whether a task has aged past its SLA (нарушение SLA, §16.4).

    ``True`` once :func:`age_hours` strictly exceeds ``sla_hours``; a task exactly
    at its deadline is still *within* SLA (``False``).
    """
    return age_hours(created_at_iso, now_iso) > sla_hours
