"""Domain taxonomy resolution (§24.3)."""

from __future__ import annotations

from kg_schema.taxonomy import load_taxonomy


def test_loads_entries() -> None:
    idx = load_taxonomy()
    assert len(idx.entries) >= 50
    # every canonical entry has at least one RU and one EN term
    for e in idx.entries:
        assert e.canonical_ru and e.canonical_en, e.id


def test_ru_en_resolve_same_entry() -> None:
    idx = load_taxonomy()
    a = idx.resolve_exact("электроэкстракция")
    b = idx.resolve_exact("electrowinning")
    assert a is not None and b is not None and a.id == b.id == "electrowinning"


def test_pvp_synonyms() -> None:
    # §24.3 acceptance: ПВП / печь взвешенной плавки / flash smelting furnace
    # all resolve to a single canonical entity.
    idx = load_taxonomy()
    ids = {
        idx.resolve_exact(s).id
        for s in ["ПВП", "печь взвешенной плавки", "flash smelting furnace"]  # type: ignore[union-attr]
    }
    assert len(ids) == 1
    assert "flash_smelting" in next(iter(ids))


def test_ion_synonyms() -> None:
    idx = load_taxonomy()
    assert idx.resolve_exact("сульфаты").id == idx.resolve_exact("SO4").id == "sulfates"
    assert idx.resolve_exact("TDS").id == idx.resolve_exact("сухой остаток").id


def test_geography_practice_type() -> None:
    idx = load_taxonomy()
    assert idx.resolve_exact("Россия").practice_type == "russia"
    assert idx.resolve_exact("Finland").practice_type == "foreign"
