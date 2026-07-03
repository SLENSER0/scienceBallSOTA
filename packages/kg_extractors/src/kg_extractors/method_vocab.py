"""Measurement-method controlled vocabulary + detector (§6.7).

Loads the externalized controlled measurement-method vocabulary
(``resources/method_vocab.yaml``) — canonical ``method_id`` -> ``canonical_ru`` /
``canonical_en`` / ``synonyms`` / ``measurand`` — into a frozen
:class:`MethodVocab`, and exposes :func:`detect_method`, which scans free text for
the leftmost controlled measurement method (``измерено по Виккерсу`` -> Vickers,
``XRD analysis`` -> XRD).

Каждый метод несёт RU- и EN-синонимы и измеряемую величину (measurand). RU-основы
сопоставляются без учёта падежа (``виккерс`` -> ``Виккерсу``); короткие
англоязычные аббревиатуры (SEM/TEM/XRD/EDS/AAS) — только по границам слов, чтобы
не срабатывать внутри более длинных токенов.

Pure python + PyYAML — no other dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "resources" / "method_vocab.yaml"

# Cyrillic letters used both to detect declinable RU stems and to consume their
# case endings (``виккерс`` -> ``виккерсу``). Matching runs case-insensitively.
_CYRILLIC = "а-яёА-ЯЁ"
_CYRILLIC_TAIL = re.compile(rf"[{_CYRILLIC}]$")


def _norm(mention: str) -> str:
    """Fold a mention for lookup: strip + lowercase (case/declension-insensitive)."""
    return str(mention).strip().lower()


def _compile_synonym(surface: str) -> re.Pattern[str] | None:
    """Compile one surface into a word-bounded, whitespace-flexible matcher (§6.7).

    Tokens are split on whitespace and re-joined with ``\\s+`` so ``ICP OES`` also
    matches ``ICP  OES``. A surface ending in a Cyrillic letter gets a trailing
    ``[а-яё]*`` so RU stems match their declensions; ASCII acronyms do not, so
    ``TEM`` never matches inside ``HRTEM`` or ``temperature``.
    """
    tokens = [t for t in surface.split() if t]
    if not tokens:
        return None
    body = r"\s+".join(re.escape(t) for t in tokens)
    tail = rf"[{_CYRILLIC}]*" if _CYRILLIC_TAIL.search(surface) else ""
    return re.compile(rf"\b{body}{tail}\b", re.IGNORECASE)


@dataclass(frozen=True)
class MethodEntry:
    """One controlled measurement method (§6.7): ids, synonyms, measurand."""

    method_id: str
    canonical_ru: str
    canonical_en: str
    synonyms: tuple[str, ...]
    measurand: str

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict (synonyms as a list)."""
        return {
            "method_id": self.method_id,
            "canonical_ru": self.canonical_ru,
            "canonical_en": self.canonical_en,
            "synonyms": list(self.synonyms),
            "measurand": self.measurand,
        }


@dataclass(frozen=True)
class MethodMatch:
    """A detected measurement method mention in free text (§6.7).

    ``surface`` is the exact substring found; ``source_span`` is ``"start:end"``
    character offsets into the scanned text.
    """

    method_id: str
    surface: str
    source_span: str

    def as_dict(self) -> dict[str, str]:
        """Serialize to a plain ``{method_id, surface, source_span}`` dict."""
        return {
            "method_id": self.method_id,
            "surface": self.surface,
            "source_span": self.source_span,
        }


@dataclass(frozen=True)
class MethodVocab:
    """In-memory controlled measurement-method vocabulary with detection (§6.7)."""

    entries: tuple[MethodEntry, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for e in self.entries:
            if not e.method_id:
                raise ValueError("method vocab: empty method_id")
            if e.method_id in seen:
                raise ValueError(f"method vocab: duplicate method_id {e.method_id!r}")
            seen.add(e.method_id)
        by_id = {e.method_id: e for e in self.entries}
        # Ordered (method_id, compiled) matchers; canonical surfaces are matched too.
        matchers: list[tuple[str, re.Pattern[str]]] = []
        for e in self.entries:
            surfaces = (e.canonical_ru, e.canonical_en, *e.synonyms)
            for s in surfaces:
                pat = _compile_synonym(s)
                if pat is not None:
                    matchers.append((e.method_id, pat))
        # Bypass frozen to cache derived indices (standard frozen-dataclass idiom).
        object.__setattr__(self, "_by_id", by_id)
        object.__setattr__(self, "_matchers", tuple(matchers))

    def __len__(self) -> int:
        return len(self.entries)

    def all_ids(self) -> tuple[str, ...]:
        """Canonical ``method_id`` values in file order (§6.7)."""
        return tuple(e.method_id for e in self.entries)

    def entry(self, method_id: str) -> MethodEntry | None:
        """Return the :class:`MethodEntry` for *method_id*, or ``None``."""
        return self._by_id.get(method_id)  # type: ignore[attr-defined]

    def synonyms(self, method_id: str) -> tuple[str, ...]:
        """RU/EN surface synonyms for *method_id* (empty for unknown id)."""
        e = self._by_id.get(method_id)  # type: ignore[attr-defined]
        return e.synonyms if e else ()

    def measurand(self, method_id: str) -> str | None:
        """Property/measurand determined by *method_id*, or ``None`` for unknown id."""
        e = self._by_id.get(method_id)  # type: ignore[attr-defined]
        return e.measurand if e else None

    def detect(self, text: str) -> MethodMatch | None:
        """Return the leftmost (then longest) detected method in *text*, else None."""
        if not text:
            return None
        best: tuple[int, int, str, str] | None = None  # (start, -len, method_id, surface)
        for method_id, pat in self._matchers:  # type: ignore[attr-defined]
            m = pat.search(text)
            if m is None:
                continue
            key = (m.start(), -(m.end() - m.start()), method_id, m.group(0))
            if best is None or key < best:
                best = key
        if best is None:
            return None
        start, neg_len, method_id, surface = best
        end = start - neg_len
        return MethodMatch(method_id=method_id, surface=surface, source_span=f"{start}:{end}")


def load_method_vocab(path: Path | str | None = None) -> MethodVocab:
    """Load the measurement-method vocabulary from YAML (§6.7).

    *path* defaults to ``resources/method_vocab.yaml`` next to this module.
    The YAML is a mapping of ``method_id`` -> entry fields.
    """
    p = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"method vocab: expected a mapping, got {type(raw).__name__}")
    entries = tuple(
        MethodEntry(
            method_id=str(mid),
            canonical_ru=str(rec.get("canonical_ru", "")),
            canonical_en=str(rec.get("canonical_en", "")),
            synonyms=tuple(str(s) for s in (rec.get("synonyms") or [])),
            measurand=str(rec.get("measurand", "")),
        )
        for mid, rec in raw.items()
    )
    return MethodVocab(entries)


@lru_cache(maxsize=1)
def default_method_vocab() -> MethodVocab:
    """Cached default measurement-method vocabulary from the packaged YAML (§6.7)."""
    return load_method_vocab()


def detect_method(text: str, vocab: MethodVocab | None = None) -> MethodMatch | None:
    """Detect the leftmost controlled measurement method in *text*, or ``None`` (§6.7).

    Uses the cached default vocabulary unless an explicit *vocab* is supplied, so
    ``detect_method("XRD analysis")`` -> ``MethodMatch(method_id='method:xrd', ...)``.
    """
    return (vocab or default_method_vocab()).detect(text)
