"""Document fingerprints — exact content hash + near-duplicate MinHash (§5.17).

Отпечатки документов: точный хеш содержимого и MinHash для почти-дубликатов.

Two deterministic, dependency-light fingerprinting helpers (stdlib ``hashlib``
only, no third-party libraries):

- :func:`content_fingerprint` — a stable SHA-256 hex digest of the
  whitespace-normalized text. Two surfaces that differ only in whitespace (extra
  spaces, tabs, newlines, leading/trailing padding) fold to the *same* digest,
  so it is an exact-content identity key that ignores cosmetic reflowing.
- :func:`near_fingerprint` — a compact hex MinHash signature over word
  3-shingles ("MinHash-lite"): a fixed bank of :data:`_NUM_PERM` seeded SHA-256
  permutations, keeping the minimum hash per permutation. Near-duplicate texts
  (small edits, reordered padding) share most signature slots.
- :func:`near_similarity` / :func:`is_near_dup` — estimate the Jaccard overlap
  of two texts from the fraction of matching MinHash slots, and threshold it.

The signature is derived purely from the normalized token stream, so both
fingerprints are fully deterministic and reproducible across processes.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Number of independent MinHash permutations (signature length). More slots ⇒
# tighter Jaccard estimate; 64 is a solid accuracy/size trade-off.
_NUM_PERM = 64
# Word-shingle width. Texts shorter than this collapse to a single whole-text
# shingle so short surfaces still get a stable, comparable signature.
_SHINGLE_K = 3
# Sentinel min-hash for an empty shingle set (no tokens). Two empty texts then
# match on every slot (similarity 1.0); an empty vs. non-empty text does not.
_EMPTY_SLOT = 0


def _normalize(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip the ends.

    Схлопывает пробелы к одиночным и обрезает края (нормализация пробелов).
    """
    return " ".join(text.split())


def _shingles(text: str) -> frozenset[str]:
    """Word ``_SHINGLE_K``-grams of the normalized text (whole text if shorter).

    Множество словных k-грамм нормализованного текста.
    """
    tokens = _normalize(text).split(" ")
    if tokens == [""]:
        return frozenset()
    if len(tokens) < _SHINGLE_K:
        return frozenset({" ".join(tokens)})
    grams = (" ".join(tokens[i : i + _SHINGLE_K]) for i in range(len(tokens) - _SHINGLE_K + 1))
    return frozenset(grams)


def _slot_hash(perm: int, shingle: str) -> int:
    """64-bit seeded hash of ``shingle`` under permutation index ``perm``.

    64-битный хеш шингла с посевом номера перестановки.
    """
    digest = hashlib.sha256(f"{perm}\x00{shingle}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _signature(text: str) -> tuple[int, ...]:
    """MinHash signature: per-permutation minimum shingle hash.

    MinHash-подпись: поминимумный хеш шинглов по каждой перестановке.
    """
    shingles = _shingles(text)
    if not shingles:
        return (_EMPTY_SLOT,) * _NUM_PERM
    return tuple(min(_slot_hash(perm, sh) for sh in shingles) for perm in range(_NUM_PERM))


@dataclass(frozen=True)
class DocFingerprint:
    """Combined exact + near fingerprints of one document (§5.17).

    Fields
    ------
    content
        Stable SHA-256 hex of the whitespace-normalized text (точный хеш).
    near
        Hex MinHash signature for near-duplicate matching (почти-дубликаты).
    """

    content: str
    near: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return asdict(self)


def content_fingerprint(text: str) -> str:
    """Stable SHA-256 hex of the whitespace-normalized ``text``.

    Стабильный SHA-256 нормализованного по пробелам текста.
    """
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def near_fingerprint(text: str) -> str:
    """Hex MinHash signature of ``text`` over word 3-shingles ("MinHash-lite").

    Hex-подпись MinHash по словным 3-шинглам ("MinHash-lite").
    """
    return "".join(f"{slot:016x}" for slot in _signature(text))


def fingerprint(text: str) -> DocFingerprint:
    """Both fingerprints of ``text`` as a frozen :class:`DocFingerprint`.

    Оба отпечатка текста как замороженный :class:`DocFingerprint`.
    """
    return DocFingerprint(content_fingerprint(text), near_fingerprint(text))


def near_similarity(a: str, b: str) -> float:
    """Estimated Jaccard overlap of ``a`` and ``b`` from matching MinHash slots.

    Оценка Жаккара по доле совпавших слотов MinHash-подписи, в ``[0, 1]``.
    """
    sig_a = _signature(a)
    sig_b = _signature(b)
    matches = sum(1 for x, y in zip(sig_a, sig_b, strict=True) if x == y)
    return matches / _NUM_PERM


def is_near_dup(a: str, b: str, threshold: float = 0.8) -> bool:
    """Whether ``a`` and ``b`` are near-duplicates at ``threshold`` (inclusive).

    Являются ли ``a`` и ``b`` почти-дубликатами при пороге ``threshold``.
    """
    return near_similarity(a, b) >= threshold
