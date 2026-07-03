"""Property vocabulary YAML loader (§6.6).

Loads the externalized controlled property vocabulary
(``resources/property_vocab.yaml``) — canonical ``property_id`` ->
``canonical_ru`` / ``canonical_en`` / ``synonyms`` / ``allowed_units`` /
``property_class`` — and exposes case- and declension-insensitive lookup
(via lowercasing) of a free-text mention to its canonical id. The synonyms
mirror ``kg_extractors.property_extractor.PROPERTY_VOCAB`` and the
``allowed_units`` mirror ``kg_common.units.policy.PROPERTY_UNIT_POLICY``,
keeping extraction, unit-gating and this vocabulary aligned.

Pure python + PyYAML — no other dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "resources" / "property_vocab.yaml"


def _norm(mention: str) -> str:
    """Fold a mention for lookup: strip + lowercase (case/declension-insensitive)."""
    return str(mention).strip().lower()


@dataclass(frozen=True)
class PropertyEntry:
    """One controlled property (§6.6): canonical ids, synonyms, units, class."""

    property_id: str
    canonical_ru: str
    canonical_en: str
    synonyms: tuple[str, ...]
    allowed_units: tuple[str, ...]
    property_class: str

    def as_dict(self) -> dict[str, object]:
        return {
            "property_id": self.property_id,
            "canonical_ru": self.canonical_ru,
            "canonical_en": self.canonical_en,
            "synonyms": list(self.synonyms),
            "allowed_units": list(self.allowed_units),
            "property_class": self.property_class,
        }


class PropertyVocabulary:
    """In-memory controlled property vocabulary with mention lookup (§6.6)."""

    def __init__(self, entries: list[PropertyEntry]) -> None:
        seen: set[str] = set()
        for e in entries:
            if not e.property_id:
                raise ValueError("property vocab: empty property_id")
            if e.property_id in seen:
                raise ValueError(f"property vocab: duplicate property_id {e.property_id!r}")
            seen.add(e.property_id)
        self._entries = list(entries)
        self._by_id: dict[str, PropertyEntry] = {e.property_id: e for e in entries}
        # lowercased surface (canonical_ru/en + synonyms) -> canonical property_id.
        self._lookup: dict[str, str] = {}
        for e in entries:
            surfaces = {e.canonical_ru, e.canonical_en, *e.synonyms}
            for s in surfaces:
                key = _norm(s)
                if key:
                    self._lookup.setdefault(key, e.property_id)

    def __len__(self) -> int:
        return len(self._entries)

    def canonical_for(self, mention: str) -> str | None:
        """Return the canonical ``property_id`` for *mention*, or ``None``.

        Exact/synonym lookup folded through :func:`_norm` (lowercased + stripped),
        so ``'Твёрдость'`` and ``'HARDNESS'`` both resolve to ``prop:hardness``.
        """
        if not mention:
            return None
        return self._lookup.get(_norm(mention))

    def all_ids(self) -> tuple[str, ...]:
        """Canonical ``property_id`` values in file order (§6.6)."""
        return tuple(e.property_id for e in self._entries)

    def entry(self, property_id: str) -> PropertyEntry | None:
        """Return the :class:`PropertyEntry` for *property_id*, or ``None``."""
        return self._by_id.get(property_id)

    def synonyms(self, property_id: str) -> tuple[str, ...]:
        """RU/EN surface synonyms for *property_id* (empty for unknown id)."""
        e = self._by_id.get(property_id)
        return e.synonyms if e else ()

    def allowed_units(self, property_id: str) -> tuple[str, ...]:
        """Allowed measurement units for *property_id* (empty for unknown id)."""
        e = self._by_id.get(property_id)
        return e.allowed_units if e else ()


def load_property_vocab(path: Path | str | None = None) -> PropertyVocabulary:
    """Load the property vocabulary from YAML (§6.6).

    *path* defaults to ``resources/property_vocab.yaml`` next to this module.
    The YAML is a mapping of ``property_id`` -> entry fields.
    """
    p = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"property vocab: expected a mapping, got {type(raw).__name__}")
    entries = [
        PropertyEntry(
            property_id=str(pid),
            canonical_ru=str(rec.get("canonical_ru", "")),
            canonical_en=str(rec.get("canonical_en", "")),
            synonyms=tuple(str(s) for s in (rec.get("synonyms") or [])),
            allowed_units=tuple(str(u) for u in (rec.get("allowed_units") or [])),
            property_class=str(rec.get("property_class", "")),
        )
        for pid, rec in raw.items()
    ]
    return PropertyVocabulary(entries)


@lru_cache(maxsize=1)
def default_property_vocab() -> PropertyVocabulary:
    """Cached default property vocabulary loaded from the packaged YAML (§6.6)."""
    return load_property_vocab()
