"""Multi-step processing-regime decomposition (§6.5)."""

from __future__ import annotations

from kg_extractors.processing_steps import ProcessingStep, decompose_processing


def test_solution_then_aging_two_ordered_steps() -> None:
    steps = decompose_processing("solution treated at 500 °C then aged at 180 °C for 2 h")
    assert len(steps) == 2
    assert [s.step_index for s in steps] == [0, 1]
    assert steps[0].operation == "solution_treatment"
    assert steps[1].operation == "aging"
    assert [s.temperature_c for s in steps] == [500.0, 180.0]
    assert steps[0].time_h is None
    assert steps[1].time_h == 2.0


def test_single_step_returns_one() -> None:
    steps = decompose_processing("Annealed at 500 °C for 1 h.")
    assert len(steps) == 1
    assert steps[0].step_index == 0
    assert steps[0].operation == "annealing"
    assert steps[0].temperature_c == 500.0
    assert steps[0].time_h == 1.0


def test_three_steps_ordered() -> None:
    text = "Homogenized at 480 °C, then quenched, then aged at 160 °C for 8 h."
    steps = decompose_processing(text)
    assert len(steps) == 3
    assert [s.operation for s in steps] == ["homogenization", "quenching", "aging"]
    assert [s.temperature_c for s in steps] == [480.0, None, 160.0]
    assert [s.step_index for s in steps] == [0, 1, 2]
    assert steps[2].time_h == 8.0


def test_atmosphere_captured_en_and_ru() -> None:
    en = decompose_processing("Annealed at 700 °C for 1 h in argon, then aged at 200 °C in air.")
    assert len(en) == 2
    assert en[0].atmosphere == "argon"
    assert en[1].atmosphere == "air"
    ru = decompose_processing("Отжиг при 650 °C в аргоне.")
    assert len(ru) == 1
    assert ru[0].operation == "annealing"
    assert ru[0].temperature_c == 650.0
    assert ru[0].atmosphere == "argon"


def test_cooling_rate_captured_not_read_as_temperature() -> None:
    steps = decompose_processing("Solution treated at 540 °C, cooled at 2 °C/min.")
    assert len(steps) == 1
    assert steps[0].operation == "solution_treatment"
    assert steps[0].temperature_c == 540.0  # NOT the 2 from "2 °C/min"
    assert steps[0].cooling_rate == 2.0


def test_no_operation_text_returns_empty() -> None:
    assert decompose_processing("Обычный текст без процессов.") == []
    assert decompose_processing("") == []
    assert decompose_processing("   ") == []
    assert decompose_processing("The sample was analyzed under a microscope.") == []


def test_step_index_contiguous() -> None:
    text = "Плавка при 1200 °C, затем электроэкстракция при 60 °C."
    steps = decompose_processing(text)
    assert len(steps) == 2
    assert [s.operation for s in steps] == ["smelting", "electrowinning"]
    assert [s.temperature_c for s in steps] == [1200.0, 60.0]
    assert [s.step_index for s in steps] == list(range(len(steps)))


def test_arrow_marker_splits_steps() -> None:
    steps = decompose_processing("Roasting at 800 °C -> leaching at 90 °C for 4 h")
    assert len(steps) == 2
    assert [s.operation for s in steps] == ["roasting", "leaching"]
    assert [s.temperature_c for s in steps] == [800.0, 90.0]
    assert steps[1].time_h == 4.0


def test_minutes_normalized_to_hours() -> None:
    steps = decompose_processing("Aged at 180 °C for 30 min.")
    assert len(steps) == 1
    assert steps[0].time_h == 0.5


def test_as_dict_exact() -> None:
    steps = decompose_processing("Aged at 180 °C for 2 h in argon.")
    assert isinstance(steps[0], ProcessingStep)
    assert steps[0].as_dict() == {
        "step_index": 0,
        "operation": "aging",
        "temperature_c": 180.0,
        "time_h": 2.0,
        "atmosphere": "argon",
        "cooling_rate": None,
        "source_span": "Aged at 180 °C for 2 h in argon.",
    }
