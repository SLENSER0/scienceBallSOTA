"""Hand-checkable tests for §12.4 Condorcet/Copeland pairwise-majority fusion."""

from __future__ import annotations

from kg_retrievers.condorcet_fusion import CondorcetHit, condorcet_fuse


def test_two_identical_sources_full_order() -> None:
    """Assertion (1): два источника [a,b,c] -> a=2, b=1, c=0 wins, порядок a,b,c."""
    hits = condorcet_fuse({"s1": ["a", "b", "c"], "s2": ["a", "b", "c"]})
    by_id = {h.doc_id: h.wins for h in hits}
    assert by_id == {"a": 2, "b": 1, "c": 0}
    assert [h.doc_id for h in hits] == ["a", "b", "c"]


def test_cyclic_pair_no_winner() -> None:
    """Assertion (2): [a,b] и [b,a] -> ничья, a.wins==0, b.wins==0, порядок a,b."""
    hits = condorcet_fuse({"s1": ["a", "b"], "s2": ["b", "a"]})
    by_id = {h.doc_id: h for h in hits}
    assert by_id["a"].wins == 0
    assert by_id["b"].wins == 0
    assert [h.doc_id for h in hits] == ["a", "b"]


def test_doc_in_single_list_still_competes() -> None:
    """Assertion (3): документ только в одном списке всё равно участвует.

    s1=[a,b], s2=[a]. Пара (a,b): s1 a<b -> a бьёт b; s2 a есть, b нет -> a бьёт b.
    relevant=2, a_beats=2 -> строгое большинство -> a побеждает b.
    """
    hits = condorcet_fuse({"s1": ["a", "b"], "s2": ["a"]})
    by_id = {h.doc_id: h for h in hits}
    assert by_id["a"].wins == 1
    assert by_id["b"].wins == 0
    assert by_id["b"].losses == 1


def test_three_source_majority() -> None:
    """Assertion (4): [a,b],[a,b],[b,a] -> a бьёт b строгим большинством, a.wins==1."""
    hits = condorcet_fuse({"s1": ["a", "b"], "s2": ["a", "b"], "s3": ["b", "a"]})
    by_id = {h.doc_id: h for h in hits}
    assert by_id["a"].wins == 1
    assert by_id["b"].wins == 0
    assert by_id["b"].losses == 1


def test_wins_plus_losses_bounded_by_other_docs() -> None:
    """Assertion (5): wins+losses <= число прочих документов для каждого хита."""
    hits = condorcet_fuse({"s1": ["a", "b", "c", "d"], "s2": ["b", "a", "d", "c"]})
    n_docs = len(hits)
    for h in hits:
        assert h.wins + h.losses <= n_docs - 1


def test_empty_input_returns_empty() -> None:
    """Assertion (6): пустой вход -> []."""
    assert condorcet_fuse({}) == []


def test_as_dict_exposes_wins_and_losses() -> None:
    """Assertion (7): as_dict() отдаёт doc_id, wins, losses."""
    hit = CondorcetHit(doc_id="a", wins=2, losses=1)
    assert hit.as_dict() == {"doc_id": "a", "wins": 2, "losses": 1}


def test_condorcet_hit_is_frozen() -> None:
    """Frozen dataclass — атрибуты неизменяемы (house style)."""
    hit = CondorcetHit(doc_id="a", wins=1, losses=0)
    try:
        hit.wins = 2  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("CondorcetHit must be frozen")


def test_sort_prefers_fewer_losses_on_wins_tie() -> None:
    """Ничья по wins разрешается меньшими losses, затем doc_id (§12.4 сортировка)."""
    # s1,s2,s3 identical [a,b,c,d]; но d проигрывает всем, a выигрывает всем.
    hits = condorcet_fuse(
        {"s1": ["a", "b", "c", "d"], "s2": ["a", "b", "c", "d"], "s3": ["a", "b", "c", "d"]}
    )
    order = [h.doc_id for h in hits]
    assert order == ["a", "b", "c", "d"]
    by_id = {h.doc_id: h for h in hits}
    assert by_id["a"].wins == 3 and by_id["a"].losses == 0
    assert by_id["d"].wins == 0 and by_id["d"].losses == 3
