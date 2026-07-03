"""Domain-glossary builder (§24.20 / §3.12).

Hand-checkable tests over a tiny temp store built directly with ``upsert_node`` so the
expected RU/EN canonical forms, aliases and definitions are known exactly. The custom
``canonical_ru`` / ``canonical_en`` / ``definition`` fields land in the ``props`` JSON
(they are not Kuzu columns) and must be read back through ``get_node`` (§3 / ADR-0005).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_common import make_id
from kg_retrievers.glossary_builder import GlossaryTerm, build_glossary
from kg_retrievers.graph_store import KuzuGraphStore

NICKEL = make_id("Material", "nickel")
COPPER = make_id("Material", "copper")
DENSITY = make_id("Property", "density")
CELL = make_id("Equipment", "diaphragm cell")
XRD = make_id("Method", "x-ray diffraction")
BARE = make_id("Material", "bare material")  # only a `name`, no canonical_ru/en props
GAP = make_id("Gap", "cold heap leaching gap")  # non-glossary label -> excluded


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    store.upsert_node(
        NICKEL,
        "Material",
        name="nickel",
        canonical_name="nickel",
        canonical_ru="Никель",
        canonical_en="Nickel",
        aliases_text="nickel|никель|Ni",
        definition="Переходный металл, Ni.",
    )
    store.upsert_node(
        COPPER,
        "Material",
        name="copper",
        canonical_ru="Медь",
        canonical_en="Copper",
        aliases_text="copper|медь|Cu",
    )
    store.upsert_node(
        DENSITY,
        "Property",
        name="density",
        canonical_ru="Плотность",
        canonical_en="Density",
        aliases_text="density|плотность",
        definition="Масса на единицу объёма.",
    )
    store.upsert_node(
        CELL,
        "Equipment",
        canonical_ru="Диафрагменная ячейка",
        canonical_en="Diaphragm cell",
        aliases_text="diaphragm cell|диафрагменная ячейка",
    )
    store.upsert_node(
        XRD,
        "Method",
        canonical_ru="Рентгеновская дифракция",
        canonical_en="X-ray diffraction",
        aliases_text="XRD|рентгеновская дифракция",
    )
    # Fallback node: only a base `name`, so RU and EN both fall back to it (§3.12).
    store.upsert_node(BARE, "Material", name="wustite")
    # A non-glossary node that must never appear in the glossary.
    store.upsert_node(GAP, "Gap", name="cold heap leaching gap")
    return store


def _by_id(terms: list[GlossaryTerm]) -> dict[str, GlossaryTerm]:
    return {t.id: t for t in terms}


def test_returns_terms_with_ru_and_en() -> None:
    store = _store()
    terms = build_glossary(store)
    by_id = _by_id(terms)
    # Every glossary label is represented; the Gap node is excluded.
    assert {NICKEL, COPPER, DENSITY, CELL, XRD, BARE} <= set(by_id)
    assert GAP not in by_id
    # Nickel carries both canonical forms and its label.
    ni = by_id[NICKEL]
    assert ni.canonical_ru == "Никель"
    assert ni.canonical_en == "Nickel"
    assert ni.type == "Material"
    # Every emitted term has a non-empty RU *and* EN surface form (bilingual glossary).
    assert all(t.canonical_ru and t.canonical_en for t in terms)


def test_fallback_to_name_when_no_canonical_props() -> None:
    store = _store()
    bare = _by_id(build_glossary(store))[BARE]
    # With only `name` set, both RU and EN fall back to it deterministically.
    assert bare.canonical_ru == "wustite"
    assert bare.canonical_en == "wustite"
    assert bare.aliases == ()


def test_q_substring_filter() -> None:
    store = _store()
    # 'медь' matches only copper (its RU form + alias); 'плот' matches only density.
    copper_terms = build_glossary(store, q="медь")
    assert [t.id for t in copper_terms] == [COPPER]
    density_terms = build_glossary(store, q="плот")
    assert [t.id for t in density_terms] == [DENSITY]
    # Substring filter is case-insensitive and also matches EN forms.
    assert [t.id for t in build_glossary(store, q="NICK")] == [NICKEL]


def test_type_filter() -> None:
    store = _store()
    methods = build_glossary(store, type="Method")
    assert [t.id for t in methods] == [XRD]
    assert all(t.type == "Method" for t in methods)
    # A type outside the four glossary labels yields nothing.
    assert build_glossary(store, type="Gap") == []


def test_aliases_populated_and_deduped() -> None:
    store = _store()
    ni = _by_id(build_glossary(store))[NICKEL]
    # aliases_text is |-split into an order-preserving tuple.
    assert ni.aliases == ("nickel", "никель", "Ni")
    assert ni.definition == "Переходный металл, Ni."


def test_limit_caps_results() -> None:
    store = _store()
    # Six glossary nodes exist; a small limit truncates after filtering, in id order.
    limited = build_glossary(store, limit=3)
    assert len(limited) == 3
    ids = [t.id for t in limited]
    assert ids == sorted(ids)
    # limit <= 0 returns nothing.
    assert build_glossary(store, limit=0) == []


def test_unknown_q_returns_empty() -> None:
    store = _store()
    assert build_glossary(store, q="квантовая криптография") == []
    assert build_glossary(store, q="zzz-no-such-term") == []


def test_as_dict_shape_and_values() -> None:
    store = _store()
    ni = _by_id(build_glossary(store))[NICKEL]
    assert ni.as_dict() == {
        "id": NICKEL,
        "type": "Material",
        "canonical_ru": "Никель",
        "canonical_en": "Nickel",
        "aliases": ["nickel", "никель", "Ni"],
        "definition": "Переходный металл, Ni.",
    }
    # Frozen: aliases is a tuple internally, exposed as a fresh list by as_dict.
    assert isinstance(ni.aliases, tuple)
    assert isinstance(ni.as_dict()["aliases"], list)
