"""Tests for the SKOS concept-scheme Turtle exporter (§22).

Тесты проверяют отображение таксономических терминов в SKOS-концепты и ручно
верифицируемую Turtle-сериализацию: заголовок ``@prefix``, объявление
``ConceptScheme``, ``skos:prefLabel``/``skos:broader``/``skos:altLabel`` и
``skos:inScheme``.
"""

from __future__ import annotations

from kg_retrievers.skos_vocabulary_export import (
    SkosConcept,
    build_concepts,
    to_turtle,
)


def _sample_concepts() -> tuple[SkosConcept, ...]:
    """A tiny materials taxonomy: a root ``oxides`` plus a child ``alumina``."""
    return build_concepts(
        [
            {"id": "oxides", "label": "Oxides"},
            {
                "id": "alumina",
                "label": "Alumina",
                "parent": "oxides",
                "aliases": ["Al2O3", "corundum"],
            },
        ]
    )


def test_build_concepts_maps_fields() -> None:
    concepts = _sample_concepts()
    assert len(concepts) == 2
    alumina = concepts[1]
    assert alumina.concept_id == "alumina"
    assert alumina.pref_label == "Alumina"
    assert alumina.broader == ("oxides",)
    assert alumina.alt_labels == ("Al2O3", "corundum")


def test_build_concepts_root_has_empty_broader() -> None:
    oxides = _sample_concepts()[0]
    assert oxides.broader == ()
    assert oxides.alt_labels == ()


def test_build_concepts_accepts_list_of_parents() -> None:
    (concept,) = build_concepts(
        [{"id": "spinel", "label": "Spinel", "parents": ["oxides", "ceramics"]}]
    )
    assert concept.broader == ("oxides", "ceramics")


def test_build_concepts_missing_id_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_concepts([{"label": "orphan"}])


def test_as_dict_broader_is_tuple() -> None:
    d = _sample_concepts()[1].as_dict()
    assert isinstance(d["broader"], tuple)
    assert d["broader"] == ("oxides",)
    assert d == {
        "concept_id": "alumina",
        "pref_label": "Alumina",
        "broader": ("oxides",),
        "alt_labels": ("Al2O3", "corundum"),
    }


def test_turtle_header_binds_skos_prefix() -> None:
    ttl = to_turtle(_sample_concepts())
    assert "@prefix skos: <http://www.w3.org/2004/02/skos/core#> ." in ttl


def test_turtle_declares_concept_scheme() -> None:
    ttl = to_turtle(_sample_concepts())
    assert ":vocab a skos:ConceptScheme ." in ttl
    # exactly one scheme declaration
    assert ttl.count("a skos:ConceptScheme") == 1


def test_turtle_pref_label_language_tagged() -> None:
    ttl = to_turtle(_sample_concepts())
    assert 'skos:prefLabel "Alumina"@en' in ttl


def test_turtle_child_emits_broader() -> None:
    ttl = to_turtle(_sample_concepts())
    assert "skos:broader :oxides" in ttl


def test_turtle_root_emits_no_broader() -> None:
    # only the root concept, so no broader statement anywhere
    ttl = to_turtle(build_concepts([{"id": "oxides", "label": "Oxides"}]))
    assert "skos:broader" not in ttl


def test_turtle_two_alt_labels_two_statements() -> None:
    ttl = to_turtle(_sample_concepts())
    assert ttl.count("skos:altLabel") == 2
    assert 'skos:altLabel "Al2O3"@en' in ttl
    assert 'skos:altLabel "corundum"@en' in ttl


def test_turtle_every_concept_in_scheme() -> None:
    concepts = _sample_concepts()
    ttl = to_turtle(concepts)
    assert ttl.count("skos:inScheme :vocab") == len(concepts)


def test_turtle_custom_scheme_id() -> None:
    ttl = to_turtle(_sample_concepts(), scheme_id="materials")
    assert ":materials a skos:ConceptScheme ." in ttl
    assert "skos:inScheme :materials" in ttl
    assert ":vocab a skos:ConceptScheme" not in ttl


def test_turtle_empty_still_declares_scheme() -> None:
    ttl = to_turtle(())
    assert ":vocab a skos:ConceptScheme ." in ttl
    assert "a skos:Concept ;" not in ttl


def test_turtle_escapes_quotes_in_label() -> None:
    (concept,) = build_concepts([{"id": "q", "label": 'the "hard" phase'}])
    ttl = to_turtle((concept,))
    assert 'skos:prefLabel "the \\"hard\\" phase"@en' in ttl
