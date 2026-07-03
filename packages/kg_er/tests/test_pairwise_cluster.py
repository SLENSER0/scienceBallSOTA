"""Tests for pure-python pairwise ER clustering (§8.4).

Ручная проверка транзитивной группировки: union-find по парам с prob >= threshold,
детерминированный порядок и агрегация min/mean по оставленным рёбрам.
"""

from __future__ import annotations

from kg_er.pairwise_cluster import ERCluster, cluster_pairs


def test_transitive_chain_merges_into_one_cluster() -> None:
    """a-b (0.95) and b-c (0.9) at threshold 0.8 -> one cluster {a,b,c}."""
    clusters = cluster_pairs([("a", "b", 0.95), ("b", "c", 0.9)], 0.8)
    assert len(clusters) == 1
    assert clusters[0].member_ids == ("a", "b", "c")
    assert clusters[0].size == 3


def test_edge_below_threshold_yields_singletons() -> None:
    """A single sub-threshold pair leaves both endpoints as singletons."""
    clusters = cluster_pairs([("a", "b", 0.6)], 0.8)
    assert len(clusters) == 2
    assert [c.member_ids for c in clusters] == [("a",), ("b",)]
    assert all(c.size == 1 for c in clusters)
    assert all(c.min_prob is None and c.mean_prob is None for c in clusters)


def test_two_components_bridged_into_size_four() -> None:
    """a-b, c-d, then bridge b-c (all kept) merge into one size-4 cluster."""
    clusters = cluster_pairs(
        [("a", "b", 0.9), ("c", "d", 0.9), ("b", "c", 0.95)],
        0.8,
    )
    assert len(clusters) == 1
    assert clusters[0].member_ids == ("a", "b", "c", "d")
    assert clusters[0].size == 4


def test_mean_prob_over_kept_edges_of_size_three_cluster() -> None:
    """Size-3 cluster's mean_prob averages its two kept edges (0.95, 0.9)."""
    clusters = cluster_pairs([("a", "b", 0.95), ("b", "c", 0.9)], 0.8)
    cluster = clusters[0]
    assert cluster.min_prob == round(0.9, 6)
    assert cluster.mean_prob == round((0.95 + 0.9) / 2, 6)


def test_all_ids_adds_isolated_singleton_with_none_probs() -> None:
    """An id in all_ids with no pairs becomes a singleton with min_prob None."""
    clusters = cluster_pairs([], 0.8, all_ids=["a", "b", "z"])
    by_member = {c.member_ids: c for c in clusters}
    assert set(by_member) == {("a",), ("b",), ("z",)}
    z_cluster = by_member[("z",)]
    assert z_cluster.size == 1
    assert z_cluster.min_prob is None
    assert z_cluster.mean_prob is None


def test_member_ids_are_sorted_and_order_is_deterministic() -> None:
    """member_ids sorted within cluster; clusters ordered by member_ids."""
    # Reversed / shuffled input must not change the deterministic output.
    clusters = cluster_pairs([("c", "a", 0.9), ("z", "y", 0.9)], 0.8)
    assert [c.member_ids for c in clusters] == [("a", "c"), ("y", "z")]
    assert [c.cluster_id for c in clusters] == [0, 1]


def test_as_dict_member_ids_is_a_list() -> None:
    """as_dict serialises member_ids as a JSON-friendly list."""
    cluster = cluster_pairs([("a", "b", 0.95)], 0.8)[0]
    data = cluster.as_dict()
    assert isinstance(data["member_ids"], list)
    assert data["member_ids"] == ["a", "b"]
    assert data["size"] == 2
    assert data["cluster_id"] == 0


def test_ercluster_is_frozen() -> None:
    """ERCluster is an immutable frozen dataclass (house style §8.4)."""
    cluster = ERCluster(0, ("a",), 1, None, None)
    try:
        cluster.size = 2  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ERCluster should be frozen")
