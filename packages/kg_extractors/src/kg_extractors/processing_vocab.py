"""Processing-operation vocabulary YAML loader (§6.5).

Loads the externalized controlled processing-operation vocabulary
(``resources/processing_vocab.yaml``) — canonical ``operation_id`` ->
``canonical_ru`` / ``canonical_en`` / ``synonyms`` / ``parameters`` / ``domain``
— and exposes case-insensitive lookup (via lowercasing) of a free-text mention
to its canonical id. The synonyms mirror the RU/EN surfaces hardcoded in
``kg_extractors.processing_extractor._METHODS`` and the ``parameters`` mirror the
process-parameter names in ``_PARAM_PATTERNS`` (temperature_c, duration,
current_density, pressure, ph). Every ``kg_schema.enums.ProcessingOperation``
value except ``other`` is covered here, keeping extraction, the enum and this
vocabulary aligned (§3.5 / §24.3).

Pure python + PyYAML — no other dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "resources" / "processing_vocab.yaml"


def _norm(mention: str) -> str:
    """Fold a mention for lookup: strip + lowercase (case-insensitive)."""
    return str(mention).strip().lower()


@dataclass(frozen=True)
class ProcessingEntry:
    """One controlled processing operation (§6.5): ids, synonyms, params, domain."""

    operation_id: str
    canonical_ru: str
    canonical_en: str
    synonyms: tuple[str, ...]
    parameters: tuple[str, ...]
    domain: str

    def as_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "canonical_ru": self.canonical_ru,
            "canonical_en": self.canonical_en,
            "synonyms": list(self.synonyms),
            "parameters": list(self.parameters),
            "domain": self.domain,
        }


class ProcessingVocabulary:
    """In-memory controlled processing-operation vocabulary with lookup (§6.5)."""

    def __init__(self, entries: list[ProcessingEntry]) -> None:
        seen: set[str] = set()
        for e in entries:
            if not e.operation_id:
                raise ValueError("processing vocab: empty operation_id")
            if e.operation_id in seen:
                raise ValueError(f"processing vocab: duplicate operation_id {e.operation_id!r}")
            seen.add(e.operation_id)
        self._entries = list(entries)
        self._by_id: dict[str, ProcessingEntry] = {e.operation_id: e for e in entries}
        # lowercased surface (canonical_ru/en + synonyms) -> canonical operation_id.
        self._lookup: dict[str, str] = {}
        for e in entries:
            surfaces = {e.canonical_ru, e.canonical_en, *e.synonyms}
            for s in surfaces:
                key = _norm(s)
                if key:
                    self._lookup.setdefault(key, e.operation_id)

    def __len__(self) -> int:
        return len(self._entries)

    def canonical_for(self, mention: str) -> str | None:
        """Return the canonical ``operation_id`` for *mention*, or ``None``.

        Exact/synonym lookup folded through :func:`_norm` (lowercased + stripped),
        so ``'Электроэкстракция'`` and ``'ELECTROWINNING'`` both resolve to
        ``'electrowinning'``.
        """
        if not mention:
            return None
        return self._lookup.get(_norm(mention))

    def all_ids(self) -> tuple[str, ...]:
        """Canonical ``operation_id`` values in file order (§6.5)."""
        return tuple(e.operation_id for e in self._entries)

    def entry(self, operation_id: str) -> ProcessingEntry | None:
        """Return the :class:`ProcessingEntry` for *operation_id*, or ``None``."""
        return self._by_id.get(operation_id)

    def synonyms(self, operation_id: str) -> tuple[str, ...]:
        """RU/EN surface synonyms for *operation_id* (empty for unknown id)."""
        e = self._by_id.get(operation_id)
        return e.synonyms if e else ()

    def typical_parameters(self, operation_id: str) -> tuple[str, ...]:
        """Typical process-parameter names for *operation_id* (empty if unknown)."""
        e = self._by_id.get(operation_id)
        return e.parameters if e else ()

    def domain(self, operation_id: str) -> str | None:
        """Metallurgical domain for *operation_id*, or ``None`` for unknown id."""
        e = self._by_id.get(operation_id)
        return e.domain if e else None


def load_processing_vocab(path: Path | str | None = None) -> ProcessingVocabulary:
    """Load the processing-operation vocabulary from YAML (§6.5).

    *path* defaults to ``resources/processing_vocab.yaml`` next to this module.
    The YAML is a mapping of ``operation_id`` -> entry fields.
    """
    p = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"processing vocab: expected a mapping, got {type(raw).__name__}")
    entries = [
        ProcessingEntry(
            operation_id=str(oid),
            canonical_ru=str(rec.get("canonical_ru", "")),
            canonical_en=str(rec.get("canonical_en", "")),
            synonyms=tuple(str(s) for s in (rec.get("synonyms") or [])),
            parameters=tuple(str(pn) for pn in (rec.get("parameters") or [])),
            domain=str(rec.get("domain", "")),
        )
        for oid, rec in raw.items()
    ]
    return ProcessingVocabulary(entries)


@lru_cache(maxsize=1)
def default_processing_vocab() -> ProcessingVocabulary:
    """Cached default processing vocabulary loaded from the packaged YAML (§6.5)."""
    return load_processing_vocab()
