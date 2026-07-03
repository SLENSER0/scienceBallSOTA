"""Processing-regime + parameter extraction (§6.5)."""

from __future__ import annotations

from kg_extractors.processing_extractor import extract_processing


def test_electrowinning_with_parameters() -> None:
    text = "Электроэкстракция никеля проводилась при 60 °C, плотности тока 250 А/м² в течение 2 ч."
    mentions = extract_processing(text)
    ew = next(m for m in mentions if m.method == "electrowinning")
    assert ew.parameters.get("temperature_c") == 60.0
    assert ew.parameters.get("current_density") == 250.0
    assert ew.parameters.get("duration") == 2.0
    assert text[ew.span[0] : ew.span[1]].lower().startswith("электроэкстракц")


def test_leaching_autoclave_pressure_ph() -> None:
    text = "Автоклавное выщелачивание вели при 180 °C, давлении 3 МПа и pH 1.5."
    methods = {m.method for m in extract_processing(text)}
    assert "autoclave_leaching" in methods or "leaching" in methods
    m = next(x for x in extract_processing(text) if x.parameters.get("pressure"))
    assert m.parameters["pressure"] == 3.0
    assert m.parameters.get("ph") == 1.5


def test_english_methods() -> None:
    mentions = extract_processing("Annealing at 500 C for 1 h, then quenching.")
    methods = {m.method for m in mentions}
    assert {"annealing", "quenching"} <= methods
    ann = next(m for m in mentions if m.method == "annealing")
    assert ann.parameters.get("temperature_c") == 500.0


def test_no_method_returns_empty() -> None:
    assert extract_processing("Обычный текст без процессов.") == []
    assert extract_processing("") == []
