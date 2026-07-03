"""Tests for per-field source provenance (§6.13 rules+ML+LLM merge).

RU: тесты происхождения поля — EN: field provenance tests.  Every assertion is
hand-checkable against the priority ``('rule', 'llm', 'ml')``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.fact_provenance import (
    DEFAULT_PRIORITY,
    FieldProvenance,
    resolve_field,
    track_provenance,
)


def test_rule_beats_llm_on_conflict() -> None:
    """Rule outranks LLM; distinct values raise ``conflict`` (§6.13)."""
    prov = resolve_field("value", [("llm", 150.0), ("rule", 148.0)])
    assert prov.source_layer == "rule"
    assert prov.value == 148.0
    assert prov.conflict is True


def test_agreeing_layers_no_conflict() -> None:
    """Equal values across layers do not flag a conflict (§6.13)."""
    prov = resolve_field("u", [("rule", "HV"), ("llm", "HV")])
    assert prov.conflict is False
    assert prov.source_layer == "rule"
    assert prov.value == "HV"


def test_single_layer_no_conflict() -> None:
    """A lone layer wins with no conflict (§6.13)."""
    prov = resolve_field("v", [("llm", 9)])
    assert prov.conflict is False
    assert prov.source_layer == "llm"
    assert prov.value == 9
    assert prov.alternatives == ()


def test_loser_recorded_in_alternatives() -> None:
    """The losing ``(layer, value)`` pair is kept as an alternative (§6.13)."""
    prov = resolve_field("value", [("llm", 150.0), ("rule", 148.0)])
    assert ("llm", 150.0) in prov.alternatives
    assert prov.alternatives == (("llm", 150.0),)


def test_unknown_layer_ranks_last() -> None:
    """A layer absent from ``priority`` loses to any named layer (§6.13)."""
    prov = resolve_field("v", [("xx", 1), ("rule", 2)])
    assert prov.source_layer == "rule"
    assert prov.value == 2
    assert prov.conflict is True
    assert prov.alternatives == (("xx", 1),)


def test_as_dict_keys() -> None:
    """``as_dict`` exposes exactly the documented provenance keys (§6.13)."""
    prov = resolve_field("v", [("rule", 1)])
    assert set(prov.as_dict()) == {
        "field",
        "value",
        "source_layer",
        "conflict",
        "alternatives",
    }


def test_as_dict_values_round_trip() -> None:
    """``as_dict`` round-trips the field values verbatim (§6.13)."""
    prov = resolve_field("value", [("llm", 150.0), ("rule", 148.0)])
    assert prov.as_dict() == {
        "field": "value",
        "value": 148.0,
        "source_layer": "rule",
        "conflict": True,
        "alternatives": (("llm", 150.0),),
    }


def test_llm_beats_ml() -> None:
    """LLM outranks ML under the default priority (§6.13)."""
    prov = resolve_field("t", [("ml", "a"), ("llm", "b")])
    assert prov.source_layer == "llm"
    assert prov.value == "b"
    assert prov.conflict is True


def test_two_unknown_layers_keep_input_order() -> None:
    """When all layers are unknown, first-supplied wins (§6.13)."""
    prov = resolve_field("w", [("aa", 1), ("bb", 2)])
    assert prov.source_layer == "aa"
    assert prov.value == 1
    assert prov.alternatives == (("bb", 2),)


def test_custom_priority_reorders_layers() -> None:
    """A caller-supplied priority overrides the default order (§6.13)."""
    prov = resolve_field("s", [("rule", 1), ("ml", 2)], priority=("ml", "llm", "rule"))
    assert prov.source_layer == "ml"
    assert prov.value == 2


def test_empty_layer_values_raises() -> None:
    """Resolving with no candidates is an error (§6.13)."""
    with pytest.raises(ValueError):
        resolve_field("x", [])


def test_track_provenance_maps_all_fields() -> None:
    """``track_provenance`` resolves each field independently (§6.13)."""
    provs = track_provenance(
        {
            "value": [("llm", 150.0), ("rule", 148.0)],
            "unit": [("rule", "HV"), ("llm", "HV")],
        }
    )
    assert set(provs) == {"value", "unit"}
    assert provs["value"].source_layer == "rule"
    assert provs["value"].conflict is True
    assert provs["unit"].conflict is False
    assert isinstance(provs["value"], FieldProvenance)


def test_frozen_dataclass_is_immutable() -> None:
    """``FieldProvenance`` is frozen (§6.13 house style)."""
    prov = resolve_field("v", [("rule", 1)])
    with pytest.raises(FrozenInstanceError):
        prov.value = 2  # type: ignore[misc]


def test_default_priority_constant() -> None:
    """The default priority is rule > llm > ml (§6.13)."""
    assert DEFAULT_PRIORITY == ("rule", "llm", "ml")
