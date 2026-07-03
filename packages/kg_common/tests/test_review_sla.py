"""Tests for SLA/aging config per task_type (§16.4) — hand-checkable values.

RU/EN: срок / SLA, возраст / age, просрочено / overdue, доля превышения /
breach ratio.
"""

from __future__ import annotations

from kg_common.storage.review_sla import (
    DEFAULT_SLA_HOURS,
    FALLBACK_SLA_HOURS,
    SlaStatus,
    evaluate,
    sla_for,
)


def test_sla_for_default_contradiction() -> None:
    """contradiction → дефолт 4 h."""
    assert sla_for("contradiction") == 4.0


def test_sla_for_unknown_falls_back() -> None:
    """Неизвестный тип → общий fallback 48 h."""
    assert sla_for("unknown_type") == 48.0
    assert FALLBACK_SLA_HOURS == 48.0


def test_sla_for_override_wins() -> None:
    """Override перекрывает дефолт."""
    assert sla_for("low_confidence", {"low_confidence": 10}) == 10.0


def test_sla_for_override_for_unknown_type() -> None:
    """Override работает и для типа без дефолта."""
    assert sla_for("custom", {"custom": 3.5}) == 3.5


def test_default_table_values() -> None:
    """Таблица дефолтов совпадает со спецификацией §16.4."""
    assert DEFAULT_SLA_HOURS == {
        "contradiction": 4.0,
        "missing_critical_field": 12.0,
        "ambiguous_er": 24.0,
        "low_confidence": 48.0,
        "low_quality_ocr": 72.0,
        "new_schema_term": 168.0,
    }


def test_evaluate_overdue_contradiction() -> None:
    """5 h возраст vs 4 h SLA → просрочено, age ровно 5.0."""
    status = evaluate(
        "contradiction",
        "2026-01-01T00:00:00Z",
        "2026-01-01T05:00:00Z",
    )
    assert status.overdue is True
    assert status.age_hours == 5.0


def test_evaluate_not_overdue_low_confidence() -> None:
    """1 h возраст vs 48 h SLA → не просрочено."""
    status = evaluate(
        "low_confidence",
        "2026-01-01T00:00:00Z",
        "2026-01-01T01:00:00Z",
    )
    assert status.overdue is False


def test_breach_ratio_age8_sla4() -> None:
    """Возраст 8 h при SLA 4 h (override) → breach_ratio 2.0."""
    status = evaluate(
        "contradiction",
        "2026-01-01T00:00:00Z",
        "2026-01-01T08:00:00Z",
        {"contradiction": 4.0},
    )
    assert status.breach_ratio == 2.0
    assert status.overdue is True


def test_overdue_boundary_equal() -> None:
    """Возраст ровно == SLA → overdue True (граница включительна)."""
    status = evaluate(
        "contradiction",
        "2026-01-01T00:00:00Z",
        "2026-01-01T04:00:00Z",
    )
    assert status.age_hours == 4.0
    assert status.overdue is True
    assert status.breach_ratio == 1.0


def test_as_dict_matches_sla_for() -> None:
    """as_dict()['sla_hours'] совпадает с sla_for для того же типа."""
    status = evaluate(
        "ambiguous_er",
        "2026-01-01T00:00:00Z",
        "2026-01-01T06:00:00Z",
    )
    dumped = status.as_dict()
    assert dumped["sla_hours"] == sla_for("ambiguous_er")
    assert dumped == {
        "task_type": "ambiguous_er",
        "age_hours": 6.0,
        "sla_hours": 24.0,
        "overdue": False,
        "breach_ratio": 0.25,
    }


def test_sla_status_is_frozen() -> None:
    """SlaStatus заморожен — нельзя мутировать."""
    status = SlaStatus("contradiction", 5.0, 4.0, True, 1.25)
    try:
        status.age_hours = 9.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("SlaStatus must be frozen")
