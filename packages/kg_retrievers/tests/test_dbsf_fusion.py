"""Hand-checkable tests for §12.4 Distribution-Based Score Fusion (DBSF)."""

from __future__ import annotations

from statistics import pstdev

from kg_retrievers.dbsf_fusion import DBSFHit, _dbsf_normalize, dbsf_fuse


def test_mean_maps_to_exactly_half() -> None:
    """Assertion (1): для {a:1,b:2,c:3} среднее b=2 → ровно 0.5."""
    norm = _dbsf_normalize({"a": 1.0, "b": 2.0, "c": 3.0})
    assert norm["b"] == 0.5


def test_below_and_above_mean_bracket_half() -> None:
    """Assertion (2): a<0.5<c вокруг среднего в {a:1,b:2,c:3}."""
    norm = _dbsf_normalize({"a": 1.0, "b": 2.0, "c": 3.0})
    assert norm["a"] < 0.5 < norm["c"]


def _symmetric_with_outliers() -> dict[str, float]:
    """20 нулей + hi=+1 + lo=-1 (n=22): std=sqrt(2/22), 3std<1 → outliers за окном."""
    src: dict[str, float] = {f"z{i:02d}": 0.0 for i in range(20)}
    src["hi"] = 1.0
    src["lo"] = -1.0
    return src


def test_value_above_window_clamps_to_one() -> None:
    """Assertion (3): score за mean+3std зажимается ровно в 1.0."""
    src = _symmetric_with_outliers()
    assert 3.0 * pstdev(src.values()) < 1.0  # hi=+1 действительно за окном
    assert _dbsf_normalize(src)["hi"] == 1.0


def test_value_below_window_clamps_to_zero() -> None:
    """Assertion (4): score за mean-3std зажимается ровно в 0.0."""
    src = _symmetric_with_outliers()
    assert _dbsf_normalize(src)["lo"] == 0.0


def test_center_of_symmetric_maps_to_half() -> None:
    """Assertion (5): нули в центре симметричного источника → 0.5."""
    assert _dbsf_normalize(_symmetric_with_outliers())["z00"] == 0.5


def test_constant_source_all_half() -> None:
    """Assertion (6): постоянный источник {x:5,y:5} (std==0) → оба 0.5."""
    assert _dbsf_normalize({"x": 5.0, "y": 5.0}) == {"x": 0.5, "y": 0.5}


def test_empty_source_normalizes_to_empty() -> None:
    """Assertion (7): пустой источник → пустой dict."""
    assert _dbsf_normalize({}) == {}


def test_doc_in_two_sources_scores_higher() -> None:
    """Assertion (8): два источника суммируются — общий doc обгоняет одиночный."""
    scores = {
        "dense": {"shared": 3.0, "only_a": 2.0, "low": 1.0},
        "sparse": {"shared": 3.0, "only_b": 2.0, "low": 1.0},
    }
    by_id = {h.doc_id: h.score for h in dbsf_fuse(scores)}
    # shared присутствует в обоих → сумма двух нормализаций > одиночного вклада.
    assert by_id["shared"] > by_id["only_a"]
    assert by_id["shared"] > by_id["only_b"]


def test_missing_source_contributes_zero() -> None:
    """Assertion (9): отсутствие doc в источнике = вклад 0 (нет в per_source)."""
    scores = {
        "dense": {"shared": 3.0, "only_a": 2.0, "low": 1.0},
        "sparse": {"shared": 3.0, "only_b": 2.0, "low": 1.0},
    }
    hit = next(h for h in dbsf_fuse(scores) if h.doc_id == "only_a")
    assert set(hit.per_source) == {"dense"}
    assert hit.score == hit.per_source["dense"]


def test_output_sorted_descending() -> None:
    """Assertion (10): итог отсортирован по убыванию score."""
    scores = {"dense": {"a": 1.0, "b": 2.0, "c": 3.0}}
    out = dbsf_fuse(scores)
    assert [h.score for h in out] == sorted((h.score for h in out), reverse=True)


def test_tie_ordered_lexicographically() -> None:
    """Assertion (11): равные score → doc_id по алфавиту ('a' раньше 'b')."""
    out = dbsf_fuse({"dense": {"b": 5.0, "a": 5.0}})
    assert [h.doc_id for h in out] == ["a", "b"]
    assert out[0].score == out[1].score == 0.5


def test_as_dict_round_trips_keys() -> None:
    """Assertion (12): as_dict() отдаёт ключи {doc_id, score, per_source}."""
    hit = DBSFHit(doc_id="d1", score=1.5, per_source={"dense": 0.75, "sparse": 0.75})
    assert hit.as_dict() == {
        "doc_id": "d1",
        "score": 1.5,
        "per_source": {"dense": 0.75, "sparse": 0.75},
    }


def test_empty_fusion_returns_empty_list() -> None:
    """Assertion (13): пустой вход → пустой список."""
    assert dbsf_fuse({}) == []
