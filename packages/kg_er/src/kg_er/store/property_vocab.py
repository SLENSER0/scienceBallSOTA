"""Controlled property vocabulary loader + validation (§8.6/§8.2).

Loads ``data/property_vocab.yaml`` (canonical_id, label, synonyms, symbols,
allowed_units, dimension), validates uniqueness/non-empty canonical ids, and
exposes exact + alias lookup for :class:`kg_er.decision.PropertyMapper`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from kg_er.comparisons.text import clean_text

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "property_vocab.yaml"


@dataclass(frozen=True)
class PropertyTerm:
    canonical_id: str
    label: str
    synonyms: tuple[str, ...]
    symbols: tuple[str, ...]
    allowed_units: tuple[str, ...]
    dimension: str | None = None


class PropertyVocabulary:
    def __init__(self, terms: list[PropertyTerm]) -> None:
        seen: set[str] = set()
        for t in terms:
            if not t.canonical_id:
                raise ValueError("property vocab: empty canonical_id")
            if t.canonical_id in seen:
                raise ValueError(f"property vocab: duplicate canonical_id {t.canonical_id!r}")
            seen.add(t.canonical_id)
        self.terms = terms
        self._exact: dict[str, str] = {}
        self._alias_index: dict[str, list[str]] = {}
        for t in terms:
            names = {t.label, *t.synonyms, *t.symbols, t.canonical_id}
            cleaned = sorted({clean_text(n) for n in names if n})
            self._alias_index[t.canonical_id] = cleaned
            for n in cleaned:
                self._exact.setdefault(n, t.canonical_id)

    def __len__(self) -> int:
        return len(self.terms)

    def lookup_exact(self, cleaned_mention: str) -> str | None:
        return self._exact.get(cleaned_mention)

    def alias_index(self) -> dict[str, list[str]]:
        return self._alias_index

    def allowed_units(self, canonical_id: str) -> tuple[str, ...]:
        for t in self.terms:
            if t.canonical_id == canonical_id:
                return t.allowed_units
        return ()

    @classmethod
    def from_yaml(cls, path: Path | str | None = None) -> PropertyVocabulary:
        p = Path(path) if path else _DEFAULT_PATH
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or []
        terms = [
            PropertyTerm(
                canonical_id=str(r["canonical_id"]),
                label=str(r.get("label", r["canonical_id"])),
                synonyms=tuple(r.get("synonyms", []) or []),
                symbols=tuple(str(s) for s in (r.get("symbols", []) or [])),
                allowed_units=tuple(r.get("allowed_units", []) or []),
                dimension=r.get("dimension"),
            )
            for r in raw
        ]
        return cls(terms)


@lru_cache(maxsize=1)
def default_vocabulary() -> PropertyVocabulary:
    return PropertyVocabulary.from_yaml()
