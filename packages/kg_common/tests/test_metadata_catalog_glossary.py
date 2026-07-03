"""Tests for the catalog business-glossary registry (§10.3)."""

from __future__ import annotations

from kg_common.metadata.catalog_glossary import (
    CORE_TERMS,
    GROUPS,
    GlossaryTerm,
    all_labels,
    term_for,
    terms_in_group,
)


def test_group_assignments() -> None:
    """Representative labels land in the expected business groups."""
    material = term_for("Material")
    claim = term_for("Claim")
    lab = term_for("Lab")
    assert material is not None and material.group == "entity"
    assert claim is not None and claim.group == "factual"
    assert lab is not None and lab.group == "org"


def test_unknown_label_is_none() -> None:
    """An unknown label resolves to None."""
    assert term_for("Nope") is None


def test_urn_format() -> None:
    """urn() emits the DataHub glossary-term URN for the label."""
    comp = term_for("Composition")
    assert comp is not None
    assert comp.urn() == "urn:li:glossaryTerm:Composition"
    assert term_for("Material").urn() == "urn:li:glossaryTerm:Material"


def test_all_labels_coverage() -> None:
    """all_labels() covers the core set and is sorted with no dupes."""
    labels = all_labels()
    assert "Material" in labels
    assert "Contradiction" in labels
    assert len(labels) >= 20
    assert list(labels) == sorted(labels)
    assert len(labels) == len(set(labels))
    assert set(labels) == set(CORE_TERMS)


def test_terms_in_group_org() -> None:
    """terms_in_group('org') returns only org terms, sorted by label."""
    org = terms_in_group("org")
    assert all(t.group == "org" for t in org)
    assert [t.label for t in org] == ["Lab", "Person", "Project", "ResearchTeam"]
    assert list(org) == sorted(org, key=lambda t: t.label)


def test_groups_partition_core_terms() -> None:
    """Every core term uses one of the three declared groups."""
    assert GROUPS == ("entity", "factual", "org")
    assert {t.group for t in CORE_TERMS.values()} == set(GROUPS)
    # Each group is non-empty and the three partition the whole catalog.
    total = sum(len(terms_in_group(g)) for g in GROUPS)
    assert total == len(CORE_TERMS)
    for g in GROUPS:
        assert len(terms_in_group(g)) > 0


def test_frozen_dataclass_and_as_dict() -> None:
    """GlossaryTerm is frozen and as_dict() is a flat field map."""
    term = term_for("Evidence")
    assert isinstance(term, GlossaryTerm)
    assert term.as_dict() == {
        "label": "Evidence",
        "group": "factual",
        "definition": term.definition,
    }
    try:
        term.label = "X"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("GlossaryTerm must be frozen")


def test_factual_group_members() -> None:
    """The evidence-bearing labels are grouped as 'factual'."""
    factual = {t.label for t in terms_in_group("factual")}
    assert {"Claim", "Finding", "Evidence", "Contradiction", "Gap"} <= factual
