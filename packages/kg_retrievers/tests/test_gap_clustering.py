"""Gap clustering by shared material / property / domain (§15.12).

Every expected cluster is hand-derivable from the composite-key fallback chain
(material+property → domain → type) and the modal-``type`` rule for the dominant
type. Fixtures are tiny so the grouping can be checked by eye.
"""

from __future__ import annotations

import pytest

from kg_retrievers.gap_clustering import (
    UNCLUSTERED_KEY,
    GapCluster,
    cluster_gaps,
    cluster_key,
    rank_clusters,
)


def _gap(gid: str, **over: object) -> dict:
    """A gap dict with an id plus optional material/property/domain/type."""
    base: dict = {"id": gid}
    base.update(over)
    return base


def test_shared_material_and_property_cluster_together() -> None:
    # Two gaps on the same material×property are the same missing measurement (§15.12).
    gaps = [
        _gap("g1", material_id="M1", property_id="P1", type="missing_value"),
        _gap("g2", material_id="M1", property_id="P1", type="missing_value"),
    ]
    clusters = cluster_gaps(gaps)
    assert len(clusters) == 1
    (cluster,) = clusters
    assert cluster.key == "material=M1|property=P1"
    assert cluster.size == 2
    assert list(cluster.gap_ids) == ["g1", "g2"]


def test_different_materials_stay_separate() -> None:
    # Same property but different materials → distinct composite keys → 2 clusters.
    gaps = [
        _gap("g1", material_id="M1", property_id="P1"),
        _gap("g2", material_id="M2", property_id="P1"),
    ]
    clusters = cluster_gaps(gaps)
    assert len(clusters) == 2
    assert {c.key for c in clusters} == {"material=M1|property=P1", "material=M2|property=P1"}
    assert all(c.size == 1 for c in clusters)


def test_dominant_type_is_the_modal_type() -> None:
    # Within one material×property cluster the dominant type is the most frequent:
    # types = [absent, absent, contradiction] → "absent" wins 2 to 1 (§15.12).
    gaps = [
        _gap("g1", material_id="M1", property_id="P1", type="absent"),
        _gap("g2", material_id="M1", property_id="P1", type="absent"),
        _gap("g3", material_id="M1", property_id="P1", type="contradiction"),
    ]
    (cluster,) = cluster_gaps(gaps)
    assert cluster.size == 3
    assert cluster.dominant_type == "absent"


def test_dominant_type_tie_breaks_to_first_seen() -> None:
    # A 1-1 tie resolves to the earliest-appearing modal type (deterministic).
    gaps = [
        _gap("g1", domain="water", type="beta"),
        _gap("g2", domain="water", type="alpha"),
    ]
    (cluster,) = cluster_gaps(gaps)
    assert cluster.key == "domain=water"
    assert cluster.dominant_type == "beta"


def test_domain_fallback_when_no_material_or_property() -> None:
    # No material/property → group by shared domain (§24), not by type.
    gaps = [
        _gap("g1", domain="desalination", type="absent"),
        _gap("g2", domain="desalination", type="stale"),
        _gap("g3", domain="membrane", type="absent"),
    ]
    clusters = {c.key: c for c in cluster_gaps(gaps)}
    assert set(clusters) == {"domain=desalination", "domain=membrane"}
    assert clusters["domain=desalination"].size == 2
    assert list(clusters["domain=desalination"].gap_ids) == ["g1", "g2"]


def test_type_fallback_and_unclustered_sentinel() -> None:
    # Only a type → key by type; nothing at all → the UNCLUSTERED_KEY sentinel.
    gaps = [
        _gap("g1", type="orphan"),
        _gap("g2", type="orphan"),
        _gap("g3"),
    ]
    clusters = {c.key: c for c in cluster_gaps(gaps)}
    assert clusters["type=orphan"].size == 2
    assert clusters[UNCLUSTERED_KEY].size == 1
    assert clusters[UNCLUSTERED_KEY].dominant_type is None


def test_singleton_clusters() -> None:
    # Three gaps that share nothing → three singleton clusters of size 1.
    gaps = [
        _gap("g1", material_id="M1", property_id="P1"),
        _gap("g2", material_id="M2", property_id="P2"),
        _gap("g3", domain="energy"),
    ]
    clusters = cluster_gaps(gaps)
    assert len(clusters) == 3
    assert all(c.size == 1 for c in clusters)


def test_empty_gaps_return_empty_list() -> None:
    assert cluster_gaps([]) == []
    assert rank_clusters([]) == []


def test_rank_clusters_by_size_descending() -> None:
    # big=3, mid=2, small=1 across three material keys; rank must be big, mid, small.
    gaps = [
        _gap("s1", material_id="S", property_id="P"),
        _gap("m1", material_id="M", property_id="P"),
        _gap("m2", material_id="M", property_id="P"),
        _gap("b1", material_id="B", property_id="P"),
        _gap("b2", material_id="B", property_id="P"),
        _gap("b3", material_id="B", property_id="P"),
    ]
    ranked = rank_clusters(cluster_gaps(gaps))
    assert [c.size for c in ranked] == [3, 2, 1]
    assert [c.key for c in ranked] == [
        "material=B|property=P",
        "material=M|property=P",
        "material=S|property=P",
    ]


def test_rank_clusters_ties_keep_input_order() -> None:
    # Two size-1 clusters tie: the stable sort preserves their first-seen order.
    clusters = cluster_gaps([_gap("g1", domain="a"), _gap("g2", domain="b")])
    ranked = rank_clusters(clusters)
    assert [c.key for c in ranked] == ["domain=a", "domain=b"]


def test_cluster_key_helper_follows_fallback_chain() -> None:
    assert cluster_key(_gap("g", material_id="M", property_id="P")) == "material=M|property=P"
    # material alone still uses the material+property tier (property blank).
    assert cluster_key(_gap("g", material_id="M")) == "material=M|property="
    assert cluster_key(_gap("g", domain="water")) == "domain=water"
    assert cluster_key(_gap("g", type="absent")) == "type=absent"
    assert cluster_key(_gap("g")) == UNCLUSTERED_KEY


def test_gap_cluster_as_dict_and_frozen() -> None:
    (cluster,) = cluster_gaps([_gap("g1", material_id="M1", property_id="P1", type="absent")])
    assert isinstance(cluster, GapCluster)
    dumped = cluster.as_dict()
    assert dumped == {
        "key": "material=M1|property=P1",
        "gap_ids": ["g1"],
        "size": 1,
        "dominant_type": "absent",
    }
    assert isinstance(dumped["gap_ids"], list)  # as_dict emits a plain list
    with pytest.raises(AttributeError):
        cluster.size = 99  # type: ignore[misc]
