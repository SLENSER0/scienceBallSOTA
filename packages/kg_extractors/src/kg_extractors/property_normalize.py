"""Property-name normalization to the controlled vocabulary (§6.9).

Maps a free-text RU/EN property surface — ``твёрдость`` / ``hardness`` /
``микротвёрдость``, ``предел прочности`` / ``tensile strength``,
``электропроводность`` / ``conductivity`` — to its canonical ``property_id`` via a
three-stage cascade: (1) exact canonical match, (2) synonym match, both folded so
case и ``ё``/``е`` не мешают, then (3) fuzzy near-miss via RapidFuzz for typos
(``hardnes`` -> ``hardness``, ``conductivty`` -> ``conductivity``). Surfaces that
match nothing above the fuzzy floor normalize to ``None`` — never guessed.

Builds on :mod:`kg_extractors.property_vocab` (its YAML loader + synonyms), which
it reuses read-only and does not modify.

Pure python + RapidFuzz — no other dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

from kg_extractors.property_vocab import PropertyVocabulary, default_property_vocab

# Fuzzy near-miss acceptance floor (0..1): below it a surface is unknown -> None.
_FUZZY_MIN_SCORE = 0.85
# Fuzzy stage ignores surfaces shorter than this (folded chars), so short acronyms
# (``hv`` / ``hb`` / ``uts`` / ``%``) never near-match an unrelated short input.
_FUZZY_MIN_LEN = 4


def _fold(surface: str) -> str:
    """Fold a surface for matching: strip, lowercase, ``ё`` -> ``е`` (case/ё-insensitive)."""
    return str(surface).strip().lower().replace("ё", "е")


@dataclass(frozen=True)
class PropertyNorm:
    """A property surface normalized to the controlled vocabulary (§6.9).

    ``property_id`` — canonical id (``prop:hardness``); ``canonical`` — its English
    canonical name (``canonical_en``); ``matched_synonym`` — the vocab surface that
    matched; ``score`` — ``1.0`` for an exact/synonym hit, ``<1.0`` for a fuzzy
    near-miss (RapidFuzz ratio / 100, rounded to 4 dp).
    """

    property_id: str
    canonical: str
    matched_synonym: str
    score: float

    def as_dict(self) -> dict[str, object]:
        """Serialize to ``{property_id, canonical, matched_synonym, score}``."""
        return {
            "property_id": self.property_id,
            "canonical": self.canonical,
            "matched_synonym": self.matched_synonym,
            "score": self.score,
        }


@dataclass(frozen=True)
class _SurfaceIndex:
    """Folded-surface index over a vocabulary: exact lookup + fuzzy candidate keys."""

    exact: dict[str, tuple[str, str]]  # folded surface -> (property_id, original surface)
    fuzzy_keys: tuple[str, ...]  # folded keys long enough for fuzzy matching


def _build_index(vocab: PropertyVocabulary) -> _SurfaceIndex:
    """Fold every canonical/synonym surface of *vocab* into a lookup index (§6.9).

    First surface to claim a folded key wins (file order: canonical_ru, canonical_en,
    then synonyms), mirroring :class:`PropertyVocabulary` collision handling.
    """
    exact: dict[str, tuple[str, str]] = {}
    for pid in vocab.all_ids():
        entry = vocab.entry(pid)
        if entry is None:
            continue
        for surface in (entry.canonical_ru, entry.canonical_en, *entry.synonyms):
            key = _fold(surface)
            if key:
                exact.setdefault(key, (pid, surface))
    fuzzy_keys = tuple(k for k in exact if len(k) >= _FUZZY_MIN_LEN)
    return _SurfaceIndex(exact=exact, fuzzy_keys=fuzzy_keys)


@lru_cache(maxsize=1)
def _default_index() -> _SurfaceIndex:
    """Cached folded-surface index over the packaged default vocabulary (§6.9)."""
    return _build_index(default_property_vocab())


def _make_norm(
    property_id: str, matched_synonym: str, score: float, vocab: PropertyVocabulary
) -> PropertyNorm:
    """Assemble a :class:`PropertyNorm`, filling ``canonical`` from ``canonical_en``."""
    entry = vocab.entry(property_id)
    canonical = entry.canonical_en if entry else ""
    return PropertyNorm(
        property_id=property_id,
        canonical=canonical,
        matched_synonym=matched_synonym,
        score=score,
    )


def normalize_property(
    surface: str, vocab: PropertyVocabulary | None = None
) -> PropertyNorm | None:
    """Normalize a RU/EN property *surface* to its canonical id, or ``None`` (§6.9).

    Cascade: exact/synonym hit (score ``1.0``), then a RapidFuzz near-miss at or
    above :data:`_FUZZY_MIN_SCORE`. Uses the cached default vocabulary unless an
    explicit *vocab* is supplied. Empty/blank input -> ``None``.
    """
    if not surface or not str(surface).strip():
        return None
    resolved = vocab if vocab is not None else default_property_vocab()
    index = _build_index(resolved) if vocab is not None else _default_index()
    folded = _fold(surface)

    # (1) exact canonical / (2) synonym match — both folded, score 1.0.
    hit = index.exact.get(folded)
    if hit is not None:
        property_id, matched = hit
        return _make_norm(property_id, matched, 1.0, resolved)

    # (3) fuzzy near-miss over long-enough surfaces.
    if len(folded) >= _FUZZY_MIN_LEN and index.fuzzy_keys:
        best = process.extractOne(folded, index.fuzzy_keys, scorer=fuzz.ratio)
        if best is not None:
            choice, raw_score, _ = best
            score = raw_score / 100.0
            if score >= _FUZZY_MIN_SCORE:
                property_id, matched = index.exact[choice]
                return _make_norm(property_id, matched, round(score, 4), resolved)

    return None
