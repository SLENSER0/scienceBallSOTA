"""Tests for retraction supersedence chains (§25.12).

Hand-checkable cases: a three-node lineage ``A→B→C`` with an active vs retracted head, a
standalone orphan, distinct-head counting, oldest-first member order, and a self-cycle
that must terminate.
"""

from __future__ import annotations

from kg_retrievers.retraction_supersedence_chain import (
    SupersedenceChain,
    SupersedenceReport,
    build_chains,
)


def _obs(oid: str, superseded_by: str | None = None, retracted: bool = False) -> dict:
    """A minimal observation dict."""
    d: dict = {"id": oid, "retracted": retracted}
    if superseded_by is not None:
        d["superseded_by"] = superseded_by
    return d


def test_three_node_chain_active_head() -> None:
    # A superseded_by B, B superseded_by C; C is the live head.
    obs = [_obs("A", "B"), _obs("B", "C"), _obs("C")]
    report = build_chains(obs)
    assert isinstance(report, SupersedenceReport)
    assert report.n_chains == 1
    chain = report.chains[0]
    assert isinstance(chain, SupersedenceChain)
    assert chain.head == "C"
    assert chain.members == ("A", "B", "C")
    assert chain.length == 3
    assert chain.active_head == "C"
    assert report.n_orphans == 0


def test_three_node_chain_retracted_head_has_no_active() -> None:
    obs = [_obs("A", "B"), _obs("B", "C"), _obs("C", retracted=True)]
    report = build_chains(obs)
    chain = report.chains[0]
    assert chain.head == "C"
    assert chain.members == ("A", "B", "C")
    assert chain.active_head is None


def test_standalone_is_orphan() -> None:
    obs = [_obs("D")]
    report = build_chains(obs)
    assert report.n_chains == 1
    chain = report.chains[0]
    assert chain.head == "D"
    assert chain.members == ("D",)
    assert chain.length == 1
    assert chain.active_head == "D"
    assert report.n_orphans == 1


def test_n_chains_equals_distinct_heads() -> None:
    # Lineage A→B→C plus standalone D → two distinct heads C and D.
    obs = [_obs("A", "B"), _obs("B", "C"), _obs("C"), _obs("D")]
    report = build_chains(obs)
    heads = {c.head for c in report.chains}
    assert heads == {"C", "D"}
    assert report.n_chains == 2
    assert report.n_chains == len(heads)
    assert report.n_orphans == 1


def test_members_are_oldest_first() -> None:
    obs = [_obs("A", "B"), _obs("B", "C"), _obs("C")]
    report = build_chains(obs)
    members = report.chains[0].members
    # A is oldest (points forward twice), C is the terminal head.
    assert members[0] == "A"
    assert members[-1] == "C"
    assert list(members) == sorted(members, key=lambda m: {"A": 0, "B": 1, "C": 2}[m])


def test_cycle_terminates() -> None:
    # A→B→A is malformed; build_chains must not loop forever.
    obs = [_obs("A", "B"), _obs("B", "A")]
    report = build_chains(obs)
    # Both nodes are accounted for exactly once across all chains.
    seen = [m for c in report.chains for m in c.members]
    assert sorted(seen) == ["A", "B"]


def test_self_supersede_is_ignored() -> None:
    # A pointing at itself is a degenerate loop → treated as its own head.
    obs = [_obs("A", "A")]
    report = build_chains(obs)
    assert report.n_chains == 1
    assert report.chains[0].head == "A"
    assert report.chains[0].members == ("A",)


def test_pointer_to_unknown_id_is_terminal() -> None:
    # A superseded_by an id not present → A is its own head.
    obs = [_obs("A", "ghost")]
    report = build_chains(obs)
    assert report.n_chains == 1
    assert report.chains[0].head == "A"
    assert report.chains[0].active_head == "A"


def test_custom_keys() -> None:
    obs = [
        {"uid": "x", "replaced_by": "y"},
        {"uid": "y"},
    ]
    report = build_chains(obs, id_key="uid", supersede_key="replaced_by")
    assert report.n_chains == 1
    assert report.chains[0].members == ("x", "y")
    assert report.chains[0].head == "y"


def test_as_dict_shapes() -> None:
    obs = [_obs("A", "B"), _obs("B", "C"), _obs("C")]
    report = build_chains(obs)
    d = report.as_dict()
    assert isinstance(d["chains"], list)
    assert d["n_chains"] == 1
    assert d["n_orphans"] == 0
    chain_d = d["chains"][0]
    assert isinstance(chain_d["members"], list)
    assert chain_d["members"] == ["A", "B", "C"]
    assert chain_d["active_head"] == "C"
