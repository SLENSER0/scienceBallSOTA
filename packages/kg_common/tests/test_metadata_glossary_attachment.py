"""Tests for glossary-term attachment to datasets (§10.3).

Проверки привязки терминов глоссария к датасетам. / Hand-checkable tests for
:mod:`kg_common.metadata.glossary_attachment`.
"""

from __future__ import annotations

import pytest

from kg_common.metadata.catalog_glossary import CORE_TERMS
from kg_common.metadata.glossary_attachment import (
    GlossaryAttachment,
    attach_terms,
    term_urn_for,
    terms_for_labels,
)


def test_term_urn_for_known_label() -> None:
    """Известная метка -> детерминированный URN. / Known label maps to its URN."""
    assert term_urn_for("Material") == "urn:li:glossaryTerm:Material"


def test_term_urn_for_unknown_label_raises() -> None:
    """Неизвестная метка -> ValueError. / Unknown label raises ValueError."""
    with pytest.raises(ValueError):
        term_urn_for("NotALabel")


def test_term_urn_for_composes_over_registry() -> None:
    """URN строится для каждой базовой метки. / A URN exists for every core label."""
    for label in CORE_TERMS:
        assert term_urn_for(label) == f"urn:li:glossaryTerm:{label}"


def test_terms_for_labels_dedup_order_preserved() -> None:
    """Дедуп с сохранением порядка. / Dedup keeps first-occurrence order."""
    assert terms_for_labels(["Material", "Alloy", "Material"]) == (
        "urn:li:glossaryTerm:Material",
        "urn:li:glossaryTerm:Alloy",
    )


def test_terms_for_labels_empty() -> None:
    """Пустой вход -> пустой кортеж. / Empty input yields empty tuple."""
    assert terms_for_labels([]) == ()


def test_terms_for_labels_unknown_raises() -> None:
    """Неизвестная метка в списке -> ValueError. / Unknown label in list raises."""
    with pytest.raises(ValueError):
        terms_for_labels(["Material", "NotALabel"])


def test_attach_terms_sets_dataset_urn() -> None:
    """Датасет URN сохраняется как есть. / Dataset URN is carried through."""
    att = attach_terms("urn:li:dataset:(x)", ["Material"])
    assert att.dataset_urn == "urn:li:dataset:(x)"
    assert att.term_urns == ("urn:li:glossaryTerm:Material",)


def test_attach_terms_empty_labels() -> None:
    """Пустые метки -> пустые term_urns. / Empty labels yield empty term_urns."""
    assert attach_terms("urn:li:dataset:(x)", []).term_urns == ()


def test_attach_terms_empty_dataset_urn_raises() -> None:
    """Пустой dataset_urn -> ValueError. / Empty dataset_urn raises ValueError."""
    with pytest.raises(ValueError):
        attach_terms("", ["Material"])


def test_attach_terms_dedups_labels() -> None:
    """attach_terms дедуплицирует метки. / attach_terms dedups labels too."""
    att = attach_terms("urn:li:dataset:(x)", ["Material", "Alloy", "Material"])
    assert att.term_urns == (
        "urn:li:glossaryTerm:Material",
        "urn:li:glossaryTerm:Alloy",
    )


def test_as_dict_term_urns_is_list() -> None:
    """as_dict сериализует term_urns как list. / as_dict emits term_urns as a list."""
    assert GlossaryAttachment("u", ("t",)).as_dict()["term_urns"] == ["t"]


def test_as_dict_full_shape() -> None:
    """as_dict содержит оба поля. / as_dict carries both fields."""
    assert GlossaryAttachment("u", ("t",)).as_dict() == {
        "dataset_urn": "u",
        "term_urns": ["t"],
    }


def test_attachment_is_frozen() -> None:
    """GlossaryAttachment неизменяем. / GlossaryAttachment is frozen/immutable."""
    att = GlossaryAttachment("u", ("t",))
    with pytest.raises(AttributeError):
        att.dataset_urn = "other"  # type: ignore[misc]
