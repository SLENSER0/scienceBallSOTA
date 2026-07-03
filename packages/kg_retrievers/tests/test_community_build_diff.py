"""Hand-checked tests for community build-to-build diff (§11.17)."""

from __future__ import annotations

import json

from kg_retrievers.community_build_diff import (
    CommunityDiff,
    diff_builds,
    jaccard,
)


def test_identical_builds_all_stable() -> None:
    # Same ids, same member sets → every community maps to itself.
    build = {
        0: {"a", "b"},
        1: {"c", "d"},
        2: {"e", "f"},
    }
    diff = diff_builds(build, {k: set(v) for k, v in build.items()})
    assert diff.stable == ((0, 0), (1, 1), (2, 2))
    assert diff.appeared == ()
    assert diff.disappeared == ()
    assert diff.merged == ()
    assert diff.split == ()


def test_new_community_appears() -> None:
    old = {0: {"a", "b"}}
    new = {0: {"a", "b"}, 1: {"x", "y"}}
    diff = diff_builds(old, new)
    assert diff.stable == ((0, 0),)
    assert diff.appeared == (1,)
    assert diff.disappeared == ()


def test_old_community_disappears() -> None:
    old = {0: {"a", "b"}, 1: {"x", "y"}}
    new = {0: {"a", "b"}}
    diff = diff_builds(old, new)
    assert diff.stable == ((0, 0),)
    assert diff.disappeared == (1,)
    assert diff.appeared == ()


def test_split_one_old_into_two_new() -> None:
    # old 0 = {a,b,c,d}; new 0 = {a,b}, new 1 = {c,d}.
    # jaccard(old0,new0) = 2/4 = 0.5, jaccard(old0,new1) = 2/4 = 0.5.
    # old 0 is the best match of both new 0 and new 1 → split.
    old = {0: {"a", "b", "c", "d"}}
    new = {0: {"a", "b"}, 1: {"c", "d"}}
    diff = diff_builds(old, new)
    assert diff.split == ((0, (0, 1)),)
    assert diff.stable == ()
    assert diff.merged == ()
    assert diff.appeared == ()
    assert diff.disappeared == ()


def test_merge_two_old_into_one_new() -> None:
    # old 0 = {a,b}, old 1 = {c,d}; new 0 = {a,b,c,d}.
    # both old best-match new 0 → merged.
    old = {0: {"a", "b"}, 1: {"c", "d"}}
    new = {0: {"a", "b", "c", "d"}}
    diff = diff_builds(old, new)
    assert diff.merged == (((0, 1), 0),)
    assert diff.stable == ()
    assert diff.split == ()
    assert diff.appeared == ()
    assert diff.disappeared == ()


def test_jaccard_bounds() -> None:
    assert jaccard({"a", "b"}, {"c", "d"}) == 0.0
    assert jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0
    # partial overlap: intersection 1, union 3.
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    # two empty sets → empty union → 0.0 (no ZeroDivisionError).
    assert jaccard(set(), set()) == 0.0


def test_as_dict_json_serializable() -> None:
    old = {0: {"a", "b", "c", "d"}, 5: {"z"}}
    new = {0: {"a", "b"}, 1: {"c", "d"}, 2: {"q"}}
    diff = diff_builds(old, new)
    payload = diff.as_dict()
    encoded = json.dumps(payload)
    restored = json.loads(encoded)
    # Round-trips through JSON and preserves the split structure.
    assert restored["split"] == [[0, [0, 1]]]
    assert restored["disappeared"] == [5]
    assert restored["appeared"] == [2]
    assert isinstance(diff, CommunityDiff)
