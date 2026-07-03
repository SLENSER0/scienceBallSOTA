"""Figure/table caption extraction — hand-checked cases (§6.11)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from kg_extractors.figure_caption import Caption, extract_captions


def test_ru_figure_hardness() -> None:
    # «Рис. 3. Зависимость твёрдости» -> figure #3 with a hardness hint.
    s = "Рис. 3. Зависимость твёрдости"
    caps = extract_captions(s)
    assert len(caps) == 1
    cap = caps[0]
    assert cap.kind == "figure"
    assert cap.number == 3
    assert cap.text == "Зависимость твёрдости"
    assert cap.measurand_hints == ("hardness",)
    assert cap.source_span == f"0:{len(s)}"


def test_en_figure_tensile_and_temperature() -> None:
    # "Figure 2: Tensile strength vs T" -> tensile (pos 0) then temperature (T).
    caps = extract_captions("Figure 2: Tensile strength vs T")
    assert len(caps) == 1
    cap = caps[0]
    assert cap.kind == "figure"
    assert cap.number == 2
    assert cap.text == "Tensile strength vs T"
    assert cap.measurand_hints == ("tensile", "temperature")


def test_ru_table_number_only() -> None:
    # «Табл. 1» -> table #1, empty body, no hints, span covers the whole opener.
    caps = extract_captions("Табл. 1")
    assert len(caps) == 1
    cap = caps[0]
    assert cap.kind == "table"
    assert cap.number == 1
    assert cap.text == ""
    assert cap.measurand_hints == ()
    assert cap.source_span == "0:7"


def test_en_table_trailing_period() -> None:
    # "Table 2." -> table #2 with an empty body after the trailing period.
    caps = extract_captions("Table 2.")
    assert len(caps) == 1
    assert caps[0].kind == "table"
    assert caps[0].number == 2
    assert caps[0].text == ""


def test_number_parsed_multi_digit_and_word_prefix() -> None:
    # Multi-digit number + spelled-out «Рисунок» prefix.
    fig = extract_captions("Рисунок 15. Микроструктура сплава")[0]
    assert fig.kind == "figure" and fig.number == 15
    # "Fig." abbreviation with no separator before the body.
    fig2 = extract_captions("Fig. 7 shows the setup")[0]
    assert fig2.kind == "figure" and fig2.number == 7
    assert fig2.text == "shows the setup"


def test_no_caption_returns_empty() -> None:
    # Measurand keywords present, but no caption opener -> nothing extracted.
    assert extract_captions("Материал показал высокую прочность при 500 °C.") == []
    assert extract_captions("") == []
    assert extract_captions("Just a paragraph without any labelled captions.") == []


def test_multiple_captions_ru_and_en() -> None:
    text = "Рис. 3. Зависимость твёрдости от температуры.\nTable 2. Composition of the alloy."
    caps = extract_captions(text)
    assert len(caps) == 2
    assert [c.kind for c in caps] == ["figure", "table"]
    assert [c.number for c in caps] == [3, 2]
    assert set(caps[0].measurand_hints) == {"hardness", "temperature"}
    assert caps[1].measurand_hints == ("composition",)
    # Spans are disjoint and ordered.
    first_end = int(caps[0].source_span.split(":")[1])
    second_start = int(caps[1].source_span.split(":")[0])
    assert first_end <= second_start


def test_composition_hint_ru_and_en() -> None:
    ru = extract_captions("Табл. 4. Химический состав сплава")[0]
    assert ru.kind == "table" and ru.number == 4
    assert ru.measurand_hints == ("composition",)
    en = extract_captions("Figure 5: Chemical composition of the alloy")[0]
    assert en.kind == "figure" and en.number == 5
    assert en.measurand_hints == ("composition",)


def test_source_span_round_trips_to_original_text() -> None:
    text = "См. Рис. 3. Зависимость твёрдости от температуры отжига"
    cap = extract_captions(text)[0]
    start, end = (int(x) for x in cap.source_span.split(":"))
    assert text[start:end].startswith("Рис. 3.")
    assert text[start:end].rstrip() == text[start:].rstrip()


def test_as_dict_shape_and_list_hints() -> None:
    cap = extract_captions("Рис. 8. Зависимость твёрдости от температуры")[0]
    d = cap.as_dict()
    assert d == {
        "kind": "figure",
        "number": 8,
        "text": "Зависимость твёрдости от температуры",
        "measurand_hints": ["hardness", "temperature"],
        "source_span": cap.source_span,
    }
    assert isinstance(d["measurand_hints"], list)


def test_caption_is_frozen() -> None:
    cap = Caption(
        kind="figure",
        number=1,
        text="x",
        measurand_hints=(),
        source_span="0:1",
    )
    try:
        cap.number = 2  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("Caption should be frozen")
