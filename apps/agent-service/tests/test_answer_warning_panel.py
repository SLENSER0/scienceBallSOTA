"""Hand-checked tests for the §13.17 warning-panel aggregate builder.

Pure-python, no store / no LLM: feed :func:`build_warning_panel` plain-dict
state fields (§13.11) and assert the exact counts and derived ``has_warnings``
flag. Каждое ожидаемое значение выписано явно, чтобы тест проверялся руками.
"""

from __future__ import annotations

from agent_service.answer_warning_panel import WarningPanel, build_warning_panel


def test_empty_state_is_all_zero_and_no_warnings() -> None:
    # Assertion (1): пустое состояние — все счётчики 0, has_warnings False.
    panel = build_warning_panel({})
    assert panel.contradictions_count == 0
    assert panel.low_confidence_count == 0
    assert panel.missing_data_count == 0
    assert panel.has_warnings is False


def test_two_contradictions_counted_and_warns() -> None:
    # Assertion (2): два противоречия -> count 2 и has_warnings True.
    state = {"contradictions": [{"id": "c1"}, {"id": "c2"}]}
    panel = build_warning_panel(state)
    assert panel.contradictions_count == 2
    assert panel.has_warnings is True


def test_low_confidence_below_threshold_counts_high_does_not() -> None:
    # Assertion (3): confidence 0.3 попадает в low, 0.8 — нет.
    state = {
        "citations": [
            {"confidence": 0.3},
            {"confidence": 0.8},
        ]
    }
    panel = build_warning_panel(state)
    assert panel.low_confidence_count == 1
    assert panel.has_warnings is True


def test_confidence_equal_to_threshold_is_not_counted() -> None:
    # Assertion (4): ровно 0.5 не считается (строго меньше порога).
    state = {"citations": [{"confidence": 0.5}]}
    panel = build_warning_panel(state, low_conf_threshold=0.5)
    assert panel.low_confidence_count == 0
    assert panel.has_warnings is False


def test_missing_gap_counts_conflicting_does_not() -> None:
    # Assertion (5): gap 'missing_baseline' -> missing_data, 'conflicting_...' нет.
    state = {
        "gaps": [
            {"type": "missing_baseline"},
            {"type": "conflicting_measurements"},
        ]
    }
    panel = build_warning_panel(state)
    assert panel.missing_data_count == 1
    assert panel.has_warnings is True


def test_has_warnings_true_when_only_missing_data() -> None:
    # Assertion (6): has_warnings True, даже если ненулевой только missing_data.
    state = {"gaps": [{"type": "missing_control_group"}]}
    panel = build_warning_panel(state)
    assert panel.contradictions_count == 0
    assert panel.low_confidence_count == 0
    assert panel.missing_data_count == 1
    assert panel.has_warnings is True


def test_as_dict_has_exactly_the_four_keys() -> None:
    # Assertion (7): as_dict — ровно четыре ключа.
    panel = WarningPanel(
        contradictions_count=1,
        low_confidence_count=2,
        missing_data_count=3,
        has_warnings=True,
    )
    assert panel.as_dict() == {
        "contradictions_count": 1,
        "low_confidence_count": 2,
        "missing_data_count": 3,
        "has_warnings": True,
    }
    assert set(panel.as_dict().keys()) == {
        "contradictions_count",
        "low_confidence_count",
        "missing_data_count",
        "has_warnings",
    }
