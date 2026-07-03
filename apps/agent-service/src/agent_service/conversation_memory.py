"""§13.15 память диалога / conversation memory (pure python).

A tiny, store-free ring of dialogue turns the agent keeps between requests so a
follow-up question can be understood in context (§13.15). Each :class:`Turn` pairs a
``role`` (``"user"`` / ``"assistant"`` / ``"system"``) with its ``content`` and is
frozen + JSON-serialisable via :meth:`Turn.as_dict`.

:class:`ConversationMemory` is an append-only log with two read views:

* :meth:`recent` — the last ``n`` turns, oldest→newest (последние реплики).
* :meth:`context_window` — the newest suffix of turns whose combined token estimate
  fits ``max_tokens``, dropping the oldest first (окно контекста / context window).

An optional ``max_turns`` cap bounds memory growth: once exceeded, the oldest turn is
evicted on each :meth:`add_turn`. Nothing here touches the graph store or an LLM, so
the whole module is unit-testable in isolation. Token cost is a deterministic
whitespace-word count (:func:`estimate_tokens`) — a coarse but hand-checkable proxy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Roles a turn may carry (роли реплики / turn roles). Others raise on ``add_turn``.
VALID_ROLES: frozenset[str] = frozenset({"user", "assistant", "system"})


def estimate_tokens(content: str) -> int:
    """Coarse token estimate: count whitespace-separated words (детерминированно).

    Deterministic and hand-checkable — ``"a b c"`` → ``3``, ``""`` / whitespace → ``0``.
    Used by :meth:`ConversationMemory.context_window` to size each turn's budget cost.
    """
    return len(content.split())


@dataclass(frozen=True)
class Turn:
    """One dialogue turn (§13.15): a ``role`` and its ``content``.

    Frozen and JSON-serialisable via :meth:`as_dict`. ``token_estimate`` exposes the
    same coarse word count :meth:`ConversationMemory.context_window` budgets against.
    """

    role: str
    content: str

    @property
    def token_estimate(self) -> int:
        """Coarse token cost of this turn's ``content`` (see :func:`estimate_tokens`)."""
        return estimate_tokens(self.content)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{role, content}`` (stable order)."""
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Turn:
        """Rebuild a :class:`Turn` from its :meth:`as_dict` form (round-trip)."""
        return cls(role=str(payload["role"]), content=str(payload["content"]))


class ConversationMemory:
    """Append-only log of dialogue :class:`Turn` s with recency read views (§13.15).

    Turns are stored oldest→newest. ``max_turns`` (if set) bounds the log: adding past
    the cap evicts the oldest turn (скользящее окно / sliding window). A cap of ``0``
    keeps nothing; ``None`` (default) is unbounded.
    """

    def __init__(self, max_turns: int | None = None) -> None:
        if max_turns is not None and max_turns < 0:
            raise ValueError("max_turns must be >= 0 or None / должно быть >= 0 или None")
        self._max_turns = max_turns
        self._turns: list[Turn] = []

    def add_turn(self, role: str, content: str) -> Turn:
        """Append a turn and return it; evict the oldest if over ``max_turns``.

        ``role`` must be one of :data:`VALID_ROLES` (иначе ошибка / else raises).
        """
        if role not in VALID_ROLES:
            raise ValueError(f"unknown role {role!r} / неизвестная роль")
        turn = Turn(role=role, content=content)
        self._turns.append(turn)
        if self._max_turns is not None:
            # Trim from the front so only the newest ``max_turns`` survive.
            while len(self._turns) > self._max_turns:
                self._turns.pop(0)
        return turn

    def __len__(self) -> int:
        return len(self._turns)

    @property
    def turns(self) -> list[Turn]:
        """A copy of all stored turns, oldest→newest (защита от мутаций / defensive copy)."""
        return list(self._turns)

    def recent(self, n: int) -> list[Turn]:
        """The last ``n`` turns, oldest→newest. ``n <= 0`` → ``[]``; over-ask → all."""
        if n <= 0:
            return []
        return list(self._turns[-n:])

    def context_window(self, max_tokens: int) -> list[Turn]:
        """Newest suffix of turns whose token estimates sum to ``<= max_tokens``.

        Walks from the newest turn backwards, accumulating :func:`estimate_tokens`; the
        oldest turns are dropped first until the budget fits (усечение старых / truncate
        oldest). A single turn larger than ``max_tokens`` is itself excluded, so the
        returned budget is never exceeded. Result is oldest→newest. ``max_tokens <= 0``
        → ``[]``.
        """
        if max_tokens <= 0:
            return []
        selected: list[Turn] = []
        used = 0
        for turn in reversed(self._turns):
            cost = turn.token_estimate
            if used + cost > max_tokens:
                break
            selected.append(turn)
            used += cost
        selected.reverse()
        return selected

    def clear(self) -> None:
        """Drop every stored turn (сброс истории / reset history)."""
        self._turns.clear()

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{max_turns, turns:[{role, content}, …]}`` (stable order)."""
        return {
            "max_turns": self._max_turns,
            "turns": [t.as_dict() for t in self._turns],
        }
