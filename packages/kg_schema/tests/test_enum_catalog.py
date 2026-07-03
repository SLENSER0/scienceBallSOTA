"""§3.20 — machine-readable enum catalog tests.

Hand-checkable: expected value tuples are copied straight from :mod:`kg_schema.enums`.
"""

from __future__ import annotations

import json

from kg_schema.enum_catalog import (
    ENUM_CATALOG,
    ENUM_ENTRIES,
    EnumEntry,
    catalog,
    to_json,
    values_of,
)
from kg_schema.enums import (
    EvidenceStrength,
    GapType,
    MetallurgicalDomain,
    VerificationLevel,
)

# The four §3.20 vocabularies that MUST be covered by the catalog.
REQUIRED_ENUMS = ("domain", "verification_level", "gap_type", "evidence_strength")


def test_catalog_has_key_enums() -> None:
    """§3.20 requires domain / verification_level / gap_type / evidence_strength."""
    cat = catalog()
    for name in REQUIRED_ENUMS:
        assert name in cat, name
        assert name in ENUM_CATALOG


def test_all_values_non_empty() -> None:
    """Every catalog entry is a non-empty tuple of non-empty string values."""
    cat = catalog()
    assert cat  # catalog itself is not empty
    for name, values in cat.items():
        assert isinstance(values, tuple), name
        assert len(values) >= 1, name
        assert all(isinstance(v, str) and v for v in values), name


def test_values_of_known_enum_concrete() -> None:
    """values_of returns the exact enum ordering for known names (§3.20)."""
    assert values_of("verification_level") == (
        "confirmed",
        "likely",
        "conflicting",
        "weakly_supported",
        "unverified",
        "obsolete",
    )
    assert values_of("domain") == (
        "hydrometallurgy",
        "pyrometallurgy",
        "environment",
        "water_treatment",
        "waste_processing",
        "mineral_processing",
        "electrometallurgy",
    )
    assert values_of("evidence_strength") == (
        "peer_reviewed",
        "patent",
        "internal_report",
        "experiment_protocol",
        "standard",
        "expert_comment",
        "unverified",
    )
    gaps = values_of("gap_type")
    assert len(gaps) == 16
    assert gaps[0] == "missing_property_value"
    assert "orphan_entity" in gaps
    assert "no_pilot_data" in gaps


def test_values_match_enum_classes() -> None:
    """Cross-check the catalog against the live enum classes it is built from."""
    assert values_of("gap_type") == tuple(m.value for m in GapType)
    assert values_of("verification_level") == tuple(m.value for m in VerificationLevel)
    assert values_of("domain") == tuple(m.value for m in MetallurgicalDomain)
    assert values_of("evidence_strength") == tuple(m.value for m in EvidenceStrength)


def test_values_of_unknown_returns_empty_tuple() -> None:
    """Unknown names yield an empty tuple, never raise (§3.20)."""
    assert values_of("does_not_exist") == ()
    assert values_of("") == ()
    assert values_of("Domain") == ()  # case-sensitive: not the same key as "domain"


def test_to_json_round_trip() -> None:
    """json.loads(to_json()) equals the catalog with tuples rendered as lists."""
    loaded = json.loads(to_json())
    expected = {name: list(values) for name, values in catalog().items()}
    assert loaded == expected
    assert loaded["verification_level"] == [
        "confirmed",
        "likely",
        "conflicting",
        "weakly_supported",
        "unverified",
        "obsolete",
    ]


def test_deterministic() -> None:
    """Repeated calls give equal results and stable key order (§3.20)."""
    assert catalog() == catalog()
    assert to_json() == to_json()
    assert list(catalog()) == list(ENUM_CATALOG)  # same order
    assert list(json.loads(to_json())) == list(ENUM_CATALOG)


def test_catalog_returns_defensive_copy() -> None:
    """Mutating the returned dict must not corrupt the module-level catalog."""
    cat = catalog()
    cat["domain"] = ("mutated",)
    cat.pop("gap_type", None)
    assert ENUM_CATALOG["domain"] == values_of("domain")
    assert "gap_type" in ENUM_CATALOG
    assert values_of("domain")[0] == "hydrometallurgy"


def test_enum_entries_align_with_catalog() -> None:
    """ENUM_ENTRIES mirror the catalog; EnumEntry.as_dict serialises cleanly."""
    assert tuple(e.name for e in ENUM_ENTRIES) == tuple(ENUM_CATALOG)
    for entry in ENUM_ENTRIES:
        assert isinstance(entry, EnumEntry)
        assert entry.values == ENUM_CATALOG[entry.name]
        assert entry.as_dict() == {"name": entry.name, "values": list(entry.values)}
    dom = next(e for e in ENUM_ENTRIES if e.name == "domain")
    assert dom.as_dict() == {
        "name": "domain",
        "values": [
            "hydrometallurgy",
            "pyrometallurgy",
            "environment",
            "water_treatment",
            "waste_processing",
            "mineral_processing",
            "electrometallurgy",
        ],
    }
