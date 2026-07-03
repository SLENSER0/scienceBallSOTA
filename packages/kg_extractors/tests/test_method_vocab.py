"""Measurement-method controlled vocabulary + detector (§6.7)."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError
from pathlib import Path

from kg_extractors.method_vocab import (
    MethodEntry,
    MethodMatch,
    default_method_vocab,
    detect_method,
    load_method_vocab,
)

_EXPECTED_IDS = {
    "method:vickers",
    "method:brinell",
    "method:rockwell",
    "method:tensile_test",
    "method:xrd",
    "method:sem",
    "method:tem",
    "method:hrtem",
    "method:eds",
    "method:icp_oes",
    "method:aas",
    "method:titration",
}

_RESOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "kg_extractors"
    / "resources"
    / "method_vocab.yaml"
)

_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")


def test_vocab_has_at_least_ten_methods() -> None:
    vocab = load_method_vocab()
    assert len(vocab) == 12
    assert len(vocab) >= 10
    assert all(isinstance(vocab.entry(i), MethodEntry) for i in vocab.all_ids())


def test_all_expected_ids_present() -> None:
    vocab = load_method_vocab()
    assert set(vocab.all_ids()) == _EXPECTED_IDS


def test_detect_vickers_measured_by_ru() -> None:
    # "measured by Vickers" in Russian, declined -> canonical Vickers method.
    match = detect_method("измерено по Виккерсу")
    assert match is not None
    assert match.method_id == "method:vickers"
    assert match.surface == "по Виккерсу"
    assert match.source_span == "9:20"
    assert match.as_dict() == {
        "method_id": "method:vickers",
        "surface": "по Виккерсу",
        "source_span": "9:20",
    }


def test_detect_xrd_analysis_en() -> None:
    match = detect_method("XRD analysis")
    assert match is not None
    assert match.method_id == "method:xrd"
    assert match.surface == "XRD"
    assert match.source_span == "0:3"


def test_detect_sem() -> None:
    match = detect_method("по данным SEM видно")
    assert match is not None
    assert match.method_id == "method:sem"
    assert match.surface == "SEM"
    assert match.source_span == "10:13"


def test_detect_tensile_ru() -> None:
    match = detect_method("проведено испытание на растяжение")
    assert match is not None
    assert match.method_id == "method:tensile_test"
    assert match.surface == "испытание на растяжение"
    assert match.source_span == "10:33"


def test_detect_icp_oes_hyphenated() -> None:
    match = detect_method("состав по ICP-OES")
    assert match is not None
    assert match.method_id == "method:icp_oes"
    assert match.surface == "ICP-OES"
    assert match.source_span == "10:17"


def test_detect_unknown_returns_none() -> None:
    assert detect_method("no method here at all") is None
    assert detect_method("") is None
    # short acronyms must not fire inside longer tokens.
    assert detect_method("temperature was 500") is None  # not TEM
    assert detect_method("the system reboots") is None  # not SEM


def test_tem_and_hrtem_are_distinct() -> None:
    tem = detect_method("изображение TEM")
    hrtem = detect_method("HRTEM показал структуру")
    assert tem is not None and tem.method_id == "method:tem"
    # "TEM" inside "HRTEM" must resolve to HRTEM, never bare TEM.
    assert hrtem is not None and hrtem.method_id == "method:hrtem"
    assert hrtem.surface == "HRTEM"


def test_detect_returns_leftmost_method() -> None:
    match = detect_method("SEM and XRD were used")
    assert match is not None
    assert match.method_id == "method:sem"
    assert match.source_span == "0:3"


def test_every_method_has_ru_and_en_synonyms() -> None:
    vocab = load_method_vocab()
    for mid in vocab.all_ids():
        syns = vocab.synonyms(mid)
        assert syns, f"no synonyms for {mid}"
        has_ru = any(_CYRILLIC.search(s) for s in syns)
        has_en = any(not _CYRILLIC.search(s) and re.search(r"[a-z]", s) for s in syns)
        assert has_ru, f"{mid} missing RU synonym"
        assert has_en, f"{mid} missing EN synonym"


def test_measurand_and_entry_fields() -> None:
    vocab = load_method_vocab()
    assert vocab.measurand("method:vickers") == "hardness"
    assert vocab.measurand("method:xrd") == "phase_composition"
    assert vocab.measurand("method:sem") == "microstructure"
    assert vocab.measurand("method:tensile_test") == "tensile_strength"
    assert vocab.measurand("method:icp_oes") == "concentration"
    assert vocab.measurand("method:unknown") is None
    vickers = vocab.entry("method:vickers")
    assert vickers is not None
    assert vickers.canonical_ru == "твёрдость по Виккерсу"
    assert vickers.canonical_en == "Vickers hardness"
    assert vickers.as_dict()["measurand"] == "hardness"
    assert "vickers" in vickers.as_dict()["synonyms"]


def test_default_cache_round_trip() -> None:
    a = default_method_vocab()
    b = default_method_vocab()
    assert a is b  # cached singleton
    assert set(a.all_ids()) == _EXPECTED_IDS
    match = detect_method("выполнено титрование")
    assert match is not None and match.method_id == "method:titration"


def test_explicit_path_matches_default() -> None:
    from_path = load_method_vocab(_RESOURCE)
    assert set(from_path.all_ids()) == set(default_method_vocab().all_ids())
    match = from_path.detect("методом AAS определили концентрацию")
    assert match is not None and match.method_id == "method:aas"


def test_methodmatch_is_frozen() -> None:
    match = MethodMatch(method_id="method:xrd", surface="XRD", source_span="0:3")
    try:
        match.method_id = "method:sem"  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("MethodMatch should be frozen")
