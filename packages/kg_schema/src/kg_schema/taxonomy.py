"""Domain taxonomy loader (§24.3): RU/EN synonym dictionaries → canonical entries.

Loads all YAML files in ``resources/domain_taxonomy/`` and builds an alias index
so any surface form (RU or EN) resolves to one canonical entry.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from importlib import resources

import yaml

from kg_common.ids import canonical_key, make_id


@dataclass(frozen=True)
class TaxonomyEntry:
    id: str
    node_type: str
    canonical_ru: str
    canonical_en: str
    aliases: tuple[str, ...] = ()
    domain: str | None = None
    material_class: str | None = None
    property_class: str | None = None
    default_unit: str | None = None
    practice_type: str | None = None
    source_file: str = ""

    @property
    def node_id(self) -> str:
        return make_id(self.node_type, self.id)

    @property
    def all_terms(self) -> list[str]:
        terms = {self.canonical_ru, self.canonical_en, *self.aliases, self.id}
        return [t for t in terms if t]


@dataclass
class TaxonomyIndex:
    entries: list[TaxonomyEntry] = field(default_factory=list)
    _by_key: dict[str, TaxonomyEntry] = field(default_factory=dict)
    _by_id: dict[str, TaxonomyEntry] = field(default_factory=dict)

    def _index(self) -> None:
        for e in self.entries:
            self._by_id[e.id] = e
            for term in e.all_terms:
                self._by_key.setdefault(canonical_key(term), e)

    def resolve_exact(self, surface: str) -> TaxonomyEntry | None:
        return self._by_key.get(canonical_key(surface))

    def by_id(self, entry_id: str) -> TaxonomyEntry | None:
        return self._by_id.get(entry_id)

    def all_keys(self) -> list[str]:
        return list(self._by_key.keys())

    def keys_to_entries(self) -> dict[str, TaxonomyEntry]:
        return dict(self._by_key)


@functools.lru_cache(maxsize=1)
def load_taxonomy() -> TaxonomyIndex:
    idx = TaxonomyIndex()
    root = resources.files("kg_schema").joinpath("resources", "domain_taxonomy")
    for item in sorted(root.iterdir(), key=lambda p: p.name):  # type: ignore[union-attr]
        if not item.name.endswith((".yaml", ".yml")):
            continue
        data = yaml.safe_load(item.read_text(encoding="utf-8")) or []
        for row in data:
            idx.entries.append(
                TaxonomyEntry(
                    id=row["id"],
                    node_type=row.get("node_type", "Material"),
                    canonical_ru=row.get("canonical_ru", ""),
                    canonical_en=row.get("canonical_en", ""),
                    aliases=tuple(row.get("aliases", [])),
                    domain=row.get("domain"),
                    material_class=row.get("material_class"),
                    property_class=row.get("property_class"),
                    default_unit=row.get("default_unit"),
                    practice_type=row.get("practice_type"),
                    source_file=item.name,
                )
            )
    idx._index()
    return idx
