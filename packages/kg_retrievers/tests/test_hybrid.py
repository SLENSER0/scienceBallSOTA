"""HybridRetriever RRF fusion (§12) — offline fakes, no model load.

These tests pin the *behavior* of :meth:`HybridRetriever.search` so the
read-concurrency optimization (running the vector + keyword channels on a small
ThreadPoolExecutor instead of a sequential for-loop) stays byte-identical to the
old semantics: same RRF rank sums, same ``payloads.setdefault`` first-wins
tie-breaking (vector before keyword), and the same degrade-on-fault behavior.
Каналы теперь запускаются параллельно, но результат слияния не меняется.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from kg_retrievers.hybrid import RRF_K, HybridRetriever


@dataclass
class _Hit:
    id: str
    payload: dict[str, Any]


class _FakeChannel:
    """Stand-in for a VectorStore/KeywordStore channel (records the search args)."""

    def __init__(
        self,
        hits: list[_Hit],
        *,
        delay: float = 0.0,
        raises: Exception | None = None,
    ) -> None:
        self._hits = hits
        self._delay = delay
        self._raises = raises
        self.calls: list[tuple[str, int]] = []

    def count(self) -> int:
        return len(self._hits)

    def search(self, query: str, limit: int) -> list[_Hit]:
        self.calls.append((query, limit))
        if self._delay:
            time.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._hits[:limit]


def test_search_rrf_fusion_and_channel_arg() -> None:
    """RRF sums 1/(RRF_K+rank) across channels; each channel is queried at limit*2."""
    vec = _FakeChannel([_Hit("a", {"src": "v"}), _Hit("b", {"src": "v"})])
    kw = _FakeChannel([_Hit("b", {"src": "k"}), _Hit("c", {"src": "k"})])
    hr = HybridRetriever(vector=vec, keyword=kw)

    out = hr.search("q", limit=2)

    # both channels are asked for limit*2 candidates
    assert vec.calls == [("q", 4)]
    assert kw.calls == [("q", 4)]

    scores = {h.id: h.score for h in out}
    # a: vector rank0; c: keyword rank1; b: vector rank1 + keyword rank0
    assert scores["b"] == 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 0)
    # limit=2 keeps the top two by fused score: b (both) then a (1/60) > c (1/61)
    assert [h.id for h in out] == ["b", "a"]


def test_payload_first_wins_is_vector_before_keyword() -> None:
    """payloads.setdefault keeps the vector payload for an id both channels return."""
    vec = _FakeChannel([_Hit("b", {"src": "vector"})])
    kw = _FakeChannel([_Hit("b", {"src": "keyword"})])
    hr = HybridRetriever(vector=vec, keyword=kw)

    out = hr.search("q", limit=5)
    assert len(out) == 1
    # vector is fused first, so its payload wins the setdefault tie-break
    assert out[0].payload == {"src": "vector"}


def test_matches_sequential_reference_across_orderings() -> None:
    """Concurrent fusion equals a straight sequential reference implementation."""

    def _sequential(
        channels: list[tuple[Any, str]], query: str, limit: int
    ) -> list[tuple[str, float, dict]]:
        ranks: dict[str, float] = {}
        payloads: dict[str, dict[str, Any]] = {}
        for channel, _name in channels:
            hits = channel.search(query, limit * 2)
            for rank, hit in enumerate(hits):
                ranks[hit.id] = ranks.get(hit.id, 0.0) + 1.0 / (RRF_K + rank)
                payloads.setdefault(hit.id, hit.payload)
        ordered = sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [(i, s, payloads.get(i, {})) for i, s in ordered]

    vec_hits = [_Hit("a", {"c": "v"}), _Hit("b", {"c": "v"}), _Hit("d", {"c": "v"})]
    kw_hits = [_Hit("b", {"c": "k"}), _Hit("c", {"c": "k"}), _Hit("a", {"c": "k"})]
    hr = HybridRetriever(vector=_FakeChannel(vec_hits), keyword=_FakeChannel(kw_hits))

    expected = _sequential(
        [(_FakeChannel(vec_hits), "vector"), (_FakeChannel(kw_hits), "keyword")], "q", 3
    )
    got = hr.search("q", limit=3)
    assert [(h.id, h.score, h.payload) for h in got] == expected


def test_one_channel_failure_degrades_not_raises() -> None:
    """A dead channel is logged and skipped; the surviving channel still answers."""
    vec = _FakeChannel([], raises=RuntimeError("qdrant down"))
    kw = _FakeChannel([_Hit("c", {"src": "k"})])
    hr = HybridRetriever(vector=vec, keyword=kw)

    out = hr.search("q", limit=3)
    assert [h.id for h in out] == ["c"]
    assert out[0].payload == {"src": "k"}


def test_missing_channels_return_empty() -> None:
    """No channels (both None) yields an empty result, no thread/pool error."""
    assert HybridRetriever(vector=None, keyword=None).search("q") == []


def test_channels_run_concurrently() -> None:
    """Wall time overlaps the two channels (~max), proving they are not sequential."""
    vec = _FakeChannel([_Hit("a", {})], delay=0.25)
    kw = _FakeChannel([_Hit("b", {})], delay=0.25)
    hr = HybridRetriever(vector=vec, keyword=kw)

    start = time.perf_counter()
    out = hr.search("q", limit=2)
    elapsed = time.perf_counter() - start

    assert {h.id for h in out} == {"a", "b"}
    # sequential would be ~0.50s; overlapped is ~0.25s. Generous margin for CI load.
    assert elapsed < 0.45
