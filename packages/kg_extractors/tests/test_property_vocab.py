"""Property vocabulary YAML + loader (§6.6)."""

from __future__ import annotations

from pathlib import Path

from kg_common.units.policy import PROPERTY_UNIT_POLICY
from kg_extractors.property_extractor import PROPERTY_VOCAB
from kg_extractors.property_vocab import (
    PropertyEntry,
    default_property_vocab,
    load_property_vocab,
)

_EXPECTED_IDS = {
    "prop:hardness",
    "prop:tensile_strength",
    "prop:yield_strength",
    "prop:elongation",
    "prop:conductivity",
    "prop:density",
    "prop:current_density",
    "prop:recovery",
    "prop:grade",
    "prop:flow_velocity",
    "prop:removal_efficiency",
    "prop:tds",
}

_RESOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "kg_extractors"
    / "resources"
    / "property_vocab.yaml"
)


def test_yaml_loads_twelve_entries() -> None:
    vocab = load_property_vocab()
    assert len(vocab) == 12
    assert all(isinstance(vocab.entry(i), PropertyEntry) for i in vocab.all_ids())
    # hand-checkable canonical fields for hardness.
    hardness = vocab.entry("prop:hardness")
    assert hardness is not None
    assert hardness.canonical_ru == "твёрдость"
    assert hardness.canonical_en == "hardness"
    assert hardness.property_class == "mechanical"


def test_canonical_for_ru_hardness() -> None:
    vocab = load_property_vocab()
    assert vocab.canonical_for("твёрдость") == "prop:hardness"


def test_canonical_for_is_case_insensitive() -> None:
    vocab = load_property_vocab()
    # lowercasing folds case for both RU and EN mentions.
    assert vocab.canonical_for("ТВЁРДОСТЬ") == "prop:hardness"
    assert vocab.canonical_for("  Hardness ") == "prop:hardness"
    assert vocab.canonical_for("Current Density") == "prop:current_density"


def test_canonical_for_unknown_returns_none() -> None:
    vocab = load_property_vocab()
    assert vocab.canonical_for("несуществующее свойство") is None
    assert vocab.canonical_for("") is None


def test_synonyms_non_empty_for_every_id() -> None:
    vocab = load_property_vocab()
    for pid in vocab.all_ids():
        assert vocab.synonyms(pid), f"synonyms empty for {pid}"
    assert "hv" in vocab.synonyms("prop:hardness")


def test_allowed_units_hardness_includes_hv() -> None:
    vocab = load_property_vocab()
    assert "HV" in vocab.allowed_units("prop:hardness")
    assert vocab.allowed_units("prop:hardness") == ("HV", "HB", "HRC")
    assert vocab.allowed_units("prop:unknown") == ()


def test_all_twelve_ids_present() -> None:
    vocab = load_property_vocab()
    assert set(vocab.all_ids()) == _EXPECTED_IDS


def test_default_cache_round_trip() -> None:
    a = default_property_vocab()
    b = default_property_vocab()
    assert a is b  # cached singleton
    assert a.canonical_for("минерализация") == "prop:tds"
    assert set(a.all_ids()) == _EXPECTED_IDS


def test_explicit_path_matches_default() -> None:
    from_path = load_property_vocab(_RESOURCE)
    assert set(from_path.all_ids()) == set(default_property_vocab().all_ids())
    assert from_path.canonical_for("grade") == "prop:grade"


def test_synonyms_mirror_property_extractor() -> None:
    vocab = load_property_vocab()
    for pid, syns in PROPERTY_VOCAB.items():
        got = {s.lower() for s in vocab.synonyms(pid)}
        assert got == set(syns), f"synonym mismatch for {pid}"


def test_allowed_units_mirror_unit_policy() -> None:
    vocab = load_property_vocab()
    for pid, spec in PROPERTY_UNIT_POLICY.items():
        if pid not in _EXPECTED_IDS:
            continue
        assert vocab.allowed_units(pid) == tuple(spec["allowed_units"])
