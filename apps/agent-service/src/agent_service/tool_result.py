"""§13.13 конверт результата инструмента / tool-result envelope (pure python).

A uniform, JSON-serialisable envelope wrapping every agent tool call (§13.6 tools →
§13.13 envelope). Instead of each tool returning its own ad-hoc ``dict``, the agent
loop wraps the call in a :class:`ToolResult` so success, failure and payload size are
described the same way everywhere:

* ``tool``     — name of the invoked tool (``"graph_search"`` …).
* ``ok``       — did the call succeed? (успех / success flag).
* ``data``     — the JSON-serialisable payload on success (``None`` on error).
* ``error``    — human-readable failure message on error (``None`` on success).
* ``summary``  — short RU/EN one-liner for the LLM/context window (никогда пусто на
  ошибке / never empty on error).
* ``data_ref`` — optional pointer to the *full* payload kept elsewhere when ``data``
  was omitted or truncated (ссылка на полные данные / reference to full data).

Nothing here touches the graph store or an LLM, so the whole module is unit-testable
without a seeded Kuzu database. :func:`ok_result` / :func:`error_result` are the two
constructors; :func:`truncate_data` caps oversized list payloads for the context
window while recording the original size in ``data_ref``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """One tool invocation's result envelope (§13.13).

    Frozen and JSON-serialisable via :meth:`as_dict`. ``tool`` and ``ok`` are always
    set; the remaining fields carry either the payload (``data`` / ``data_ref``) or
    the failure (``error``), plus a short ``summary`` for the agent's context window.
    """

    tool: str
    ok: bool
    data: Any = None
    error: str | None = None
    summary: str = ""
    data_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{tool, ok, data, error, summary, data_ref}`` (stable order)."""
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "summary": self.summary,
            "data_ref": self.data_ref,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ToolResult:
        """Rebuild a :class:`ToolResult` from its :meth:`as_dict` form (round-trip).

        Tolerant of missing optional keys — only ``tool``/``ok`` carry weight and even
        those degrade to safe defaults (``""`` / ``False``) rather than raising.
        """
        return cls(
            tool=str(payload.get("tool", "")),
            ok=bool(payload.get("ok", False)),
            data=payload.get("data"),
            error=payload.get("error"),
            summary=str(payload.get("summary", "")),
            data_ref=payload.get("data_ref"),
        )


def ok_result(tool: str, data: Any, summary: str) -> ToolResult:
    """Build a successful envelope: ``ok=True``, payload in ``data``, no ``error``."""
    return ToolResult(tool=tool, ok=True, data=data, error=None, summary=summary)


def error_result(tool: str, error: str) -> ToolResult:
    """Build a failed envelope: ``ok=False``, no ``data``; ``summary`` echoes ``error``.

    The error message is copied into ``summary`` so the agent always has a non-empty
    one-liner to surface (без данных, но с причиной / no data, but a reason given).
    """
    return ToolResult(tool=tool, ok=False, data=None, error=error, summary=error)


def truncate_data(result: ToolResult, max_items: int) -> ToolResult:
    """Cap list-shaped ``data`` to ``max_items``, recording the drop in ``data_ref``.

    Returns ``result`` unchanged (the same object) when ``data`` is not a list or is
    already within the cap. Otherwise returns a NEW envelope (frozen → immutable)
    whose ``data`` keeps the first ``max_items`` elements and whose ``data_ref`` notes
    the original length (``"truncated:<n>"``), so the caller can fetch the full
    payload by reference. Negative caps are clamped to ``0`` (пустой список / empty).
    """
    data = result.data
    if not isinstance(data, list):
        return result
    cap = max(0, max_items)
    if len(data) <= cap:
        return result
    return replace(result, data=data[:cap], data_ref=f"truncated:{len(data)}")
