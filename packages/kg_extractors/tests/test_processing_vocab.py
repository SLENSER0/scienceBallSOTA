"""Processing-operation vocabulary YAML + loader (§6.5)."""

from __future__ import annotations

from pathlib import Path

from kg_extractors.processing_extractor import _METHODS, _PARAM_PATTERNS
from kg_extractors.processing_vocab import (
    ProcessingEntry,
    default_processing_vocab,
    load_processing_vocab,
)
from kg_schema.enums import ProcessingOperation

# The 23 canonical operation ids the vocab must define (§6.5).
_EXPECTED_IDS = {
    "electrowinning",
    "electrorefining",
    "leaching",
    "heap_leaching",
    "bioleaching",
    "flotation",
    "flash_smelting",
    "fluidized_bed",
    "smelting",
    "converting",
    "roasting",
    "desalination",
    "reverse_osmosis",
    "ion_exchange",
    "electrodialysis",
    "nanofiltration",
    "lime_softening",
    "gas_cleaning",
    "so2_removal",
    "water_injection",
    "aging",
    "annealing",
    "quenching",
}

_RESOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "kg_extractors"
    / "resources"
    / "processing_vocab.yaml"
)


def test_yaml_loads_all_entries() -> None:
    vocab = load_processing_vocab()
    assert len(vocab) == len(_EXPECTED_IDS)
    assert set(vocab.all_ids()) == _EXPECTED_IDS
    assert all(isinstance(vocab.entry(i), ProcessingEntry) for i in vocab.all_ids())
    # hand-checkable canonical fields for electrowinning.
    ew = vocab.entry("electrowinning")
    assert ew is not None
    assert ew.canonical_ru == "электроэкстракция"
    assert ew.canonical_en == "electrowinning"
    assert ew.domain == "electrometallurgy"
    assert ew.as_dict()["operation_id"] == "electrowinning"


def test_canonical_for_ru_electrowinning() -> None:
    vocab = load_processing_vocab()
    assert vocab.canonical_for("электроэкстракция") == "electrowinning"
    # case folding: uppercased RU and EN both resolve.
    assert vocab.canonical_for("ЭЛЕКТРОЭКСТРАКЦИЯ") == "electrowinning"
    assert vocab.canonical_for("  Electrowinning ") == "electrowinning"


def test_canonical_for_unknown_returns_none() -> None:
    vocab = load_processing_vocab()
    assert vocab.canonical_for("несуществующая операция") is None
    assert vocab.canonical_for("") is None


def test_synonyms_non_empty_for_every_id() -> None:
    vocab = load_processing_vocab()
    for oid in vocab.all_ids():
        assert vocab.synonyms(oid), f"synonyms empty for {oid}"
    assert "ew" in {s.lower() for s in vocab.synonyms("electrowinning")}


def test_typical_parameters_electrowinning_has_current_or_temperature() -> None:
    vocab = load_processing_vocab()
    params = vocab.typical_parameters("electrowinning")
    assert params, "electrowinning has no typical parameters"
    assert "current_density" in params
    assert "temperature_c" in params
    # unknown id yields an empty tuple, not an error.
    assert vocab.typical_parameters("nonexistent") == ()


def test_all_enum_ids_covered() -> None:
    vocab = load_processing_vocab()
    ids = set(vocab.all_ids())
    enum_ids = {op.value for op in ProcessingOperation} - {ProcessingOperation.OTHER.value}
    # every ProcessingOperation value (bar ``other``) has a vocabulary entry.
    assert enum_ids <= ids, f"uncovered enum ids: {enum_ids - ids}"


def test_default_cache_round_trip() -> None:
    a = default_processing_vocab()
    b = default_processing_vocab()
    assert a is b  # cached singleton
    assert a.canonical_for("выщелачивание") == "leaching"
    assert set(a.all_ids()) == _EXPECTED_IDS


def test_explicit_path_matches_default() -> None:
    from_path = load_processing_vocab(_RESOURCE)
    assert set(from_path.all_ids()) == set(default_processing_vocab().all_ids())
    assert from_path.canonical_for("флотация") == "flotation"
    assert from_path.canonical_for("обжиг") == "roasting"


def test_synonyms_mirror_processing_extractor_surfaces() -> None:
    # Each ``_METHODS`` surface whose canonical is in the vocab must be reachable:
    # some vocab synonym starts with that (stemmed) surface, keeping the extractor
    # and this vocabulary aligned (§6.5).
    vocab = load_processing_vocab()
    ids = set(vocab.all_ids())
    for surface, canon in _METHODS.items():
        if canon not in ids:
            continue  # extractor-only canonicals (electrolysis, cementation, ...)
        entry = vocab.entry(canon)
        surfaces = {entry.canonical_ru.lower(), entry.canonical_en.lower()}
        surfaces |= {s.lower() for s in vocab.synonyms(canon)}
        assert any(s.startswith(surface) for s in surfaces), f"{surface!r} unmirrored for {canon}"


def test_parameters_mirror_extractor_param_names() -> None:
    # Every ``_PARAM_PATTERNS`` name is used by at least one operation (§6.5).
    vocab = load_processing_vocab()
    used: set[str] = set()
    for oid in vocab.all_ids():
        used.update(vocab.typical_parameters(oid))
    for name, _pat in _PARAM_PATTERNS:
        assert name in used, f"extractor param {name!r} not used by any operation"


def test_domain_lookup() -> None:
    vocab = load_processing_vocab()
    assert vocab.domain("reverse_osmosis") == "water_treatment"
    assert vocab.domain("smelting") == "pyrometallurgy"
    assert vocab.domain("unknown") is None
