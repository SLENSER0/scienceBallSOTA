"""GraphRAG build cost accounting (§11.4/§11.13).

Where :mod:`graphrag_cost_estimate` gives a cheap *pre-run* arithmetic estimate
(``token_usage=0`` — no real calls happen), this module is a *post-run* accumulator: it
folds the *actual* LLM calls and token counts emitted by each build stage so §11.4's
requirement to «логировать суммарное число LLM-вызовов и токенов на build» can be met.

Каждый этап (entities, relationships, community reports, ...) issues some number of LLM
calls and consumes prompt/completion tokens. :func:`accumulate_cost` sums those raw
per-event records into one :class:`BuildCost` totalling calls and tokens across the whole
build and keeping a per-stage token breakdown for cost attribution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildCost:
    """Actual accumulated cost of one GraphRAG build (§11.4/§11.13).

    ``total_calls`` — сумма LLM-вызовов across every stage; ``prompt_tokens`` /
    ``completion_tokens`` — summed input/output tokens; ``total_tokens`` — their sum;
    ``per_stage`` — maps stage name -> that stage's total tokens (prompt + completion).
    """

    total_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    per_stage: dict[str, int]

    def as_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "per_stage": dict(self.per_stage),
        }


def accumulate_cost(events: Sequence[Mapping]) -> BuildCost:
    """Sum per-stage LLM usage events into one :class:`BuildCost` (§11.4/§11.13).

    Each event is a mapping with keys ``stage``, ``calls``, ``prompt_tokens`` and
    ``completion_tokens``. Events are summed across the whole build; events sharing a
    ``stage`` fold into a single ``per_stage`` entry holding that stage's total tokens
    (prompt + completion). An empty sequence yields all-zero totals and ``per_stage={}``.
    """
    total_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    per_stage: dict[str, int] = {}
    for event in events:
        stage = event["stage"]
        calls = event["calls"]
        prompt = event["prompt_tokens"]
        completion = event["completion_tokens"]
        total_calls += calls
        prompt_tokens += prompt
        completion_tokens += completion
        per_stage[stage] = per_stage.get(stage, 0) + prompt + completion
    return BuildCost(
        total_calls=total_calls,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        per_stage=per_stage,
    )
