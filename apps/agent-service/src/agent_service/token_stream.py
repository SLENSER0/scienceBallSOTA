"""§13.22 стриминг — сборщик дельт токенов / streaming — token delta assembler.

The ``answer_synthesizer`` LLM streams its answer as a series of ``token`` events;
the UI reassembles them into the final text. This module owns the pure, LLM-free
half of that contract: the delta→text accumulation (аккумуляция дельт) and the
projection of a delta list into ``token`` events for the transport.

Nothing here calls an LLM or touches the graph store, so the whole module stays
unit-testable без сети / without a network:

* :class:`TokenStreamState` — immutable accumulator ``(text, count, done)``.
* :func:`append_token` — fold one delta into a NEW state (пустая дельта → no-op).
* :func:`finalize` — mark the stream done (поток завершён), keeping the text.
* :func:`assemble` — fold a delta list from an empty state into the final text.
* :func:`to_token_events` — project non-empty deltas into ``token`` events.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

# Event type emitted per streamed delta (тип события / event type on the wire).
_TOKEN_EVENT = "token"


@dataclass(frozen=True)
class TokenStreamState:
    """Immutable accumulator for a streamed answer (§13.22).

    ``text`` is the concatenation of every non-empty delta seen so far
    (собранный текст / assembled text); ``count`` is how many deltas were folded
    in (число токенов); ``done`` flags a finalized stream (поток завершён).
    """

    text: str = ""
    count: int = 0
    done: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{text, count, done}`` (для транспорта / for the wire)."""
        return {"text": self.text, "count": self.count, "done": self.done}


def append_token(state: TokenStreamState, delta: str) -> TokenStreamState:
    """Fold one ``delta`` into a NEW state, concatenating text and bumping ``count``.

    A falsy / empty ``delta`` (пустая дельта) is a no-op: the same ``state`` is
    returned unchanged, so heartbeat / keep-alive frames never inflate ``count``.
    The input ``state`` is never mutated (frozen dataclass → new instance).
    """
    if not delta:
        return state
    return replace(state, text=state.text + delta, count=state.count + 1)


def finalize(state: TokenStreamState) -> TokenStreamState:
    """Return a NEW state with ``done=True`` (поток завершён), preserving text/count."""
    return replace(state, done=True)


def assemble(deltas: list[str]) -> str:
    """Fold ``deltas`` from an empty state into the final assembled text (§13.22).

    Empty and falsy deltas are skipped (see :func:`append_token`); an empty list
    yields ``""`` (пустой поток / empty stream).
    """
    state = TokenStreamState()
    for delta in deltas:
        state = append_token(state, delta)
    return state.text


def to_token_events(deltas: list[str]) -> list[dict]:
    """Project ``deltas`` into ``token`` events, one per non-empty delta (§13.22).

    Each non-empty delta becomes ``{'type': 'token', 'data': {'index': i, 'text':
    delta}}`` where ``index`` increases monotonically from ``0`` across the emitted
    events (пустые дельты пропускаются → indices stay gap-free / no gaps).
    """
    events: list[dict] = []
    for delta in deltas:
        if not delta:
            continue
        events.append({"type": _TOKEN_EVENT, "data": {"index": len(events), "text": delta}})
    return events
