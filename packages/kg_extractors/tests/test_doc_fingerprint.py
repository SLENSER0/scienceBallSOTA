"""Document-fingerprint tests — exact hash + near-duplicate MinHash (§5.17)."""

from __future__ import annotations

from kg_extractors.doc_fingerprint import (
    DocFingerprint,
    content_fingerprint,
    fingerprint,
    is_near_dup,
    near_fingerprint,
    near_similarity,
)

# Known-good constants (independently reproducible via ``sha256(normalized)``).
_EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_HELLO_SHA = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

_DOG = "The quick brown fox jumps over the lazy dog"
_DOG_EDIT = "The quick brown fox leaps over the lazy dog"  # one word changed
_UNRELATED = "Completely unrelated content about metallurgy alloys"

# ---------------------------------------------------------------------------
# content_fingerprint — exact-content SHA-256
# ---------------------------------------------------------------------------


def test_content_identical_same() -> None:
    assert content_fingerprint(_DOG) == content_fingerprint(_DOG)


def test_content_hello_world_constant() -> None:
    assert content_fingerprint("hello world") == _HELLO_SHA


def test_content_whitespace_normalized_same() -> None:
    messy = "  hello\t\tworld  \n"
    assert content_fingerprint(messy) == _HELLO_SHA
    assert content_fingerprint("hello   world") == content_fingerprint("hello world")


def test_content_different_different() -> None:
    assert content_fingerprint("hello world") != content_fingerprint("goodbye world")


def test_content_empty_constant() -> None:
    assert content_fingerprint("") == _EMPTY_SHA
    assert content_fingerprint("   \t\n  ") == _EMPTY_SHA


def test_content_deterministic_across_calls() -> None:
    first = content_fingerprint(_DOG)
    assert all(content_fingerprint(_DOG) == first for _ in range(5))


# ---------------------------------------------------------------------------
# near_fingerprint / near_similarity — MinHash-lite
# ---------------------------------------------------------------------------


def test_near_fingerprint_shape_and_determinism() -> None:
    sig = near_fingerprint(_DOG)
    assert len(sig) == 64 * 16  # 64 permutations × 16 hex chars each
    assert near_fingerprint(_DOG) == sig  # deterministic


def test_near_identical_same_signature_and_similarity() -> None:
    reflowed = "  The quick brown  fox jumps over the lazy dog "
    assert near_fingerprint(_DOG) == near_fingerprint(reflowed)
    assert near_similarity(_DOG, _DOG) == 1.0


def test_near_dup_detection_similarity() -> None:
    # One word differs among nine → 2/4 shingles shared, MinHash estimates 0.4375.
    assert near_similarity(_DOG, _DOG_EDIT) == 0.4375
    assert is_near_dup(_DOG, _DOG_EDIT, threshold=0.3) is True


def test_near_similarity_threshold_boundary() -> None:
    # Same 0.4375 pair: passes at/below the estimate, fails above it.
    assert is_near_dup(_DOG, _DOG_EDIT, threshold=0.4375) is True
    assert is_near_dup(_DOG, _DOG_EDIT, threshold=0.5) is False


def test_near_unrelated_not_dup() -> None:
    assert near_similarity(_DOG, _UNRELATED) == 0.0
    assert is_near_dup(_DOG, _UNRELATED, threshold=0.5) is False


def test_near_empty_pairs() -> None:
    assert near_similarity("", "") == 1.0  # two empties fold together
    assert near_similarity("", _DOG) == 0.0  # empty vs. content share nothing
    assert near_fingerprint("") == near_fingerprint("   ")  # deterministic empty


# ---------------------------------------------------------------------------
# DocFingerprint dataclass
# ---------------------------------------------------------------------------


def test_fingerprint_dataclass_as_dict() -> None:
    fp = fingerprint("hello world")
    assert isinstance(fp, DocFingerprint)
    assert fp.content == _HELLO_SHA
    assert fp.as_dict() == {"content": _HELLO_SHA, "near": near_fingerprint("hello world")}
