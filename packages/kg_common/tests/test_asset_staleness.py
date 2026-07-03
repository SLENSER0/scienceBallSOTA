"""Tests for asset staleness / rematerialization — тесты устаревания (§9.8)."""

from __future__ import annotations

from kg_common.asset_staleness import Staleness, is_stale, newest, stale_assets


def test_is_stale_never_materialized() -> None:
    """None asset_last is always stale — не материализован → устарел."""
    assert is_stale(None, {}) is True


def test_is_stale_upstream_older() -> None:
    """Older upstream keeps the asset fresh — апстрим старше → свежий."""
    assert is_stale(100.0, {"u": 50.0}) is False


def test_is_stale_upstream_newer() -> None:
    """Newer upstream makes the asset stale — апстрим новее → устарел."""
    assert is_stale(100.0, {"u": 150.0}) is True


def test_is_stale_no_upstreams() -> None:
    """No upstreams → a materialized asset is fresh — нет апстримов → свежий."""
    assert is_stale(100.0, {}) is False


def test_is_stale_equal_timestamp_is_fresh() -> None:
    """Equal timestamp is not strictly newer — равное время → свежий."""
    assert is_stale(100.0, {"u": 100.0}) is False


def test_is_stale_any_of_many_upstreams() -> None:
    """One newer upstream among many marks stale — любой новее → устарел."""
    assert is_stale(100.0, {"a": 10.0, "b": 200.0, "c": 5.0}) is True


def test_newest_returns_max() -> None:
    """newest returns the maximum timestamp — максимум времени."""
    assert newest({"a": 1.0, "b": 3.0}) == 3.0


def test_newest_empty_is_none() -> None:
    """newest of empty mapping is None — пусто → None."""
    assert newest({}) is None


def test_newest_single() -> None:
    """newest of one entry is that entry — один элемент."""
    assert newest({"only": 42.0}) == 42.0


def test_stale_assets_upstream_newer() -> None:
    """Downstream older than upstream → upstream_newer verdict."""
    verdicts = stale_assets({"d": 100.0, "u": 150.0}, {"d": ("u",)})
    assert verdicts[0].stale is True
    assert verdicts[0].reason == "upstream_newer"
    assert verdicts[0].asset_key == "d"


def test_stale_assets_one_per_key() -> None:
    """Exactly one verdict per key in deps — по одному вердикту на ключ."""
    verdicts = stale_assets(
        {"d": 100.0, "u": 50.0, "e": None},
        {"d": ("u",), "e": ("u",)},
    )
    assert len(verdicts) == 2
    keys = {v.asset_key for v in verdicts}
    assert keys == {"d", "e"}


def test_stale_assets_fresh() -> None:
    """Downstream newer than upstream → fresh — свежий вердикт."""
    verdicts = stale_assets({"d": 200.0, "u": 50.0}, {"d": ("u",)})
    assert verdicts[0].stale is False
    assert verdicts[0].reason == "fresh"


def test_stale_assets_never_materialized() -> None:
    """None asset timestamp → never_materialized — не материализован."""
    verdicts = stale_assets({"d": None, "u": 50.0}, {"d": ("u",)})
    assert verdicts[0].stale is True
    assert verdicts[0].reason == "never_materialized"


def test_stale_assets_missing_upstream_ignored() -> None:
    """An unbuilt upstream cannot make the asset stale — апстрим не собран."""
    # 'u' has no timestamp in materialized → ignored → asset is fresh.
    verdicts = stale_assets({"d": 100.0}, {"d": ("u",)})
    assert verdicts[0].stale is False
    assert verdicts[0].reason == "fresh"


def test_stale_assets_none_upstream_ignored() -> None:
    """A None-valued upstream is ignored — None-апстрим игнорируется."""
    verdicts = stale_assets({"d": 100.0, "u": None}, {"d": ("u",)})
    assert verdicts[0].stale is False
    assert verdicts[0].reason == "fresh"


def test_stale_assets_root_no_deps() -> None:
    """A root with no deps and a timestamp is fresh — корень свежий."""
    verdicts = stale_assets({"r": 10.0}, {"r": ()})
    assert verdicts[0].stale is False
    assert verdicts[0].reason == "fresh"


def test_stale_assets_root_never_materialized() -> None:
    """A never-built root is stale as never_materialized — корень не собран."""
    verdicts = stale_assets({"r": None}, {"r": ()})
    assert verdicts[0].stale is True
    assert verdicts[0].reason == "never_materialized"


def test_staleness_as_dict() -> None:
    """as_dict yields the exact JSON view — словарь ровно из трёх полей."""
    assert Staleness("x", False, "fresh").as_dict() == {
        "asset_key": "x",
        "stale": False,
        "reason": "fresh",
    }


def test_staleness_frozen() -> None:
    """Staleness is immutable — вердикт неизменяем."""
    verdict = Staleness("x", True, "upstream_newer")
    try:
        verdict.stale = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("Staleness should be frozen")
