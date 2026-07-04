"""M-33 + M-25 regression for the advisor candidate-evaluation agents.

M-33: a failed / malformed LLM eval must NOT fabricate ``fit_score=50``; it is
      degraded to a graph-only card (``evaluated=False``, ``fit_score=0``) that
      ranks strictly below every actually-scored candidate.
M-25: the fan-out is bounded — a hanging agent is degraded on timeout instead of
      hanging the generator forever.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from agent_service import advisor
from agent_service.advisor import AdvisorCandidate, _evaluate_candidate, _rank_key, _stream_cards


class _FakeLLM:
    def __init__(self, payload, *, delay: float = 0.0, raise_exc: bool = False) -> None:
        self._payload = payload
        self._delay = delay
        self._raise = raise_exc
        self.used_models = ["fake-model"]

    def complete_json(self, user, *, system=None, model=None, max_tokens=None):
        if self._delay:
            time.sleep(self._delay)
        if self._raise:
            raise RuntimeError("boom")
        return self._payload


def _patch_llm(monkeypatch, llm) -> None:
    monkeypatch.setattr("kg_extractors.llm.get_llm", lambda: llm)


def _intent() -> SimpleNamespace:
    return SimpleNamespace(domains=[], entities=[], numeric_constraints=[])


def _sol(sid: str = "t:1", name: str = "обратный осмос") -> dict:
    return {
        "id": sid,
        "name": name,
        "practice_type": "russia",
        "domain": "water",
        "measurements": [],
        "limitations": ["дорого"],
        "applicability": [],
    }


# --- M-33 -------------------------------------------------------------------
def test_good_eval_is_scored_and_clamped(monkeypatch) -> None:
    _patch_llm(monkeypatch, _FakeLLM({"fit_score": 150, "verdict": "ok", "supports": ["s"]}))
    card = _evaluate_candidate(_sol(), "осмос", "нет", {"осмос"}, _intent())
    assert card.evaluated is True
    assert card.fit_score == 100  # clamped into 0..100
    assert card.verdict == "ok"


def test_malformed_eval_is_not_fabricated_50(monkeypatch) -> None:
    _patch_llm(monkeypatch, _FakeLLM("not-a-dict"))
    card = _evaluate_candidate(_sol(), "осмос", "нет", {"осмос"}, _intent())
    assert card.evaluated is False
    assert card.fit_score == 0  # NOT the old fake 50
    assert "недоступна" in card.verdict


def test_dict_without_fit_score_is_degraded(monkeypatch) -> None:
    _patch_llm(monkeypatch, _FakeLLM({"verdict": "x", "supports": ["y"]}))
    card = _evaluate_candidate(_sol(), "осмос", "нет", {"осмос"}, _intent())
    assert card.evaluated is False
    assert card.fit_score == 0


def test_raising_eval_is_degraded(monkeypatch) -> None:
    _patch_llm(monkeypatch, _FakeLLM(None, raise_exc=True))
    card = _evaluate_candidate(_sol(), "осмос", "нет", {"осмос"}, _intent())
    assert card.evaluated is False
    assert card.fit_score == 0


def test_unevaluated_cards_rank_below_evaluated() -> None:
    scored_offtopic = AdvisorCandidate(
        id="a", name="a", practice_type="x", fit_score=10, verdict="", relevance=0, evaluated=True
    )
    failed_ontopic = AdvisorCandidate(
        id="b", name="b", practice_type="x", fit_score=0, verdict="", relevance=2, evaluated=False
    )
    ranked = sorted([failed_ontopic, scored_offtopic], key=_rank_key, reverse=True)
    # even though the failed card is on-topic (relevance 2), a scored card wins.
    assert [c.id for c in ranked] == ["a", "b"]


# --- M-25 -------------------------------------------------------------------
def test_stream_cards_times_out_gracefully(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "_EVAL_TIMEOUT_S", 0.3)
    _patch_llm(monkeypatch, _FakeLLM({"fit_score": 80}, delay=5.0))
    started = time.monotonic()
    cards = list(_stream_cards([_sol("t:1"), _sol("t:2")], "осмос", "нет", {"осмос"}, _intent()))
    elapsed = time.monotonic() - started
    assert elapsed < 2.5  # did not wait for the 5s-hanging agents
    assert len(cards) == 2
    assert all(c.evaluated is False and c.fit_score == 0 for c in cards)


def test_stream_cards_yields_all_on_success(monkeypatch) -> None:
    _patch_llm(monkeypatch, _FakeLLM({"fit_score": 70, "verdict": "ok"}))
    cards = list(_stream_cards([_sol("t:1"), _sol("t:2")], "осмос", "нет", {"осмос"}, _intent()))
    assert len(cards) == 2
    assert all(c.evaluated is True and c.fit_score == 70 for c in cards)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
