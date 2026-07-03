"""Hand-checkable tests for §12.4 SimHash near-duplicate clustering."""

from __future__ import annotations

from kg_retrievers.simhash_dedup import (
    SimHashCluster,
    cluster_near_dupes,
    hamming,
    simhash,
)

_BITS = 64
_TEXT_A = "the quick brown fox jumps over the lazy dog near the river bank"
_TEXT_B = "the quick brown fox jumps over the lazy dog near the river shore"  # 1-word edit
_TEXT_UNREL = "financial quarterly earnings report exceeded analyst expectations sharply"


def test_simhash_deterministic() -> None:
    assert simhash(_TEXT_A) == simhash(_TEXT_A)


def test_fingerprint_fits_in_bits() -> None:
    fp = simhash(_TEXT_A, bits=_BITS)
    assert 0 <= fp < (1 << _BITS)


def test_empty_text_is_zero() -> None:
    assert simhash("   ...  ") == 0


def test_hamming_reflexive_and_symmetric() -> None:
    x = simhash(_TEXT_A)
    y = simhash(_TEXT_B)
    assert hamming(x, x) == 0
    assert hamming(x, y) == hamming(y, x)


def test_hamming_known_value() -> None:
    # 0b1011 ^ 0b0001 = 0b1010 -> two set bits
    assert hamming(0b1011, 0b0001) == 2


def test_identical_texts_hamming_zero_one_cluster() -> None:
    docs = {"d1": _TEXT_A, "d2": _TEXT_A}
    assert hamming(simhash(_TEXT_A), simhash(_TEXT_A)) == 0
    clusters = cluster_near_dupes(docs, max_hamming=0)
    assert len(clusters) == 1
    assert set(clusters[0].member_ids) == {"d1", "d2"}


def test_one_word_edit_small_hamming_clusters() -> None:
    dist = hamming(simhash(_TEXT_A), simhash(_TEXT_B))
    assert dist <= 12  # generous threshold: near-dupe stays close
    docs = {"d1": _TEXT_A, "d2": _TEXT_B}
    clusters = cluster_near_dupes(docs, max_hamming=12)
    assert len(clusters) == 1


def test_unrelated_texts_separate_clusters() -> None:
    dist = hamming(simhash(_TEXT_A), simhash(_TEXT_UNREL))
    assert dist > 3  # unrelated -> above tight threshold
    docs = {"d1": _TEXT_A, "d2": _TEXT_UNREL}
    clusters = cluster_near_dupes(docs, max_hamming=3)
    assert len(clusters) == 2


def test_rep_is_max_score_member() -> None:
    docs = {"d1": _TEXT_A, "d2": _TEXT_A, "d3": _TEXT_A}
    scores = {"d1": 0.1, "d2": 0.9, "d3": 0.5}
    clusters = cluster_near_dupes(docs, max_hamming=0, scores=scores)
    assert len(clusters) == 1
    assert clusters[0].rep_id == "d2"
    assert clusters[0].fingerprint == simhash(_TEXT_A)


def test_rep_defaults_to_first_id_without_scores() -> None:
    docs = {"z": _TEXT_A, "a": _TEXT_A}
    clusters = cluster_near_dupes(docs, max_hamming=0)
    assert clusters[0].rep_id == "z"  # insertion order, not lexicographic


def test_as_dict_exposes_fields() -> None:
    cluster = SimHashCluster(rep_id="d1", member_ids=("d1", "d2"), fingerprint=42)
    assert cluster.as_dict() == {
        "rep_id": "d1",
        "member_ids": ("d1", "d2"),
        "fingerprint": 42,
    }


def test_transitive_grouping() -> None:
    # A~B (1-word edit) and B~A' should collapse into one cluster
    docs = {"d1": _TEXT_A, "d2": _TEXT_B, "d3": _TEXT_A}
    clusters = cluster_near_dupes(docs, max_hamming=12)
    assert len(clusters) == 1
    assert set(clusters[0].member_ids) == {"d1", "d2", "d3"}
