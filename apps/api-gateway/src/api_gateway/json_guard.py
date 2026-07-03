"""JSON body depth / size / node-count guard (§14.2 / §14.12).

Защита от «раздутого» JSON: чрезмерная вложенность или количество узлов.
The transport-level byte cap lives in
:func:`~api_gateway.error_catalog.enforce_size` (it only inspects the
``Content-Length`` header), which cannot see *structural* abuse — a small
payload can still nest thousands of levels deep or fan out into a huge tree
that explodes the parser / validator. This module closes that gap once the
body is already decoded into Python objects.

* :class:`JsonLimits`   — frozen (max_bytes, max_depth, max_nodes) budget.
* :class:`JsonTooDeep`  — raised when nesting exceeds ``max_depth``.
* :class:`JsonTooLarge` — raised when raw byte size exceeds ``max_bytes``.
* :func:`json_depth`    — container-nesting depth of a decoded object.
* :func:`count_nodes`   — total scalars + containers in a decoded object.
* :func:`enforce_json_limits` — assert a decoded body fits the budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JsonLimits:
    """Immutable JSON-shape budget for one request (§14.2).

    ``max_bytes`` bounds the raw (undecoded) body size, ``max_depth`` the
    container-nesting depth and ``max_nodes`` the total visited node count.
    """

    max_bytes: int
    max_depth: int
    max_nodes: int

    def as_dict(self) -> dict[str, int]:
        """Structured view of this budget — лимиты JSON (§14.2)."""
        return {
            "max_bytes": self.max_bytes,
            "max_depth": self.max_depth,
            "max_nodes": self.max_nodes,
        }


class JsonTooDeep(ValueError):
    """Decoded JSON nests deeper than ``max_depth`` — чрезмерная вложенность (§14.2)."""


class JsonTooLarge(ValueError):
    """Raw JSON body exceeds ``max_bytes`` — тело запроса слишком велико (§14.2)."""


def json_depth(obj: Any) -> int:
    """Container-nesting depth of a decoded JSON value (§14.2).

    Scalars (``None`` / ``bool`` / ``int`` / ``float`` / ``str``) have depth 0;
    each ``dict`` or ``list`` level adds one. Empty containers count as depth 1.
    ``json_depth({'a': {'b': 1}}) == 2``; ``json_depth([1, [2, [3]]]) == 3``.
    """
    if isinstance(obj, dict):
        if not obj:
            return 1
        return 1 + max(json_depth(value) for value in obj.values())
    if isinstance(obj, list):
        if not obj:
            return 1
        return 1 + max(json_depth(item) for item in obj)
    return 0


def count_nodes(obj: Any) -> int:
    """Total number of nodes (scalars + containers) visited (§14.2).

    Every container counts as one node plus the sum of its children; every
    scalar counts as one. ``count_nodes([1, 2, 3]) == 4`` (list + three ints).
    """
    if isinstance(obj, dict):
        return 1 + sum(count_nodes(value) for value in obj.values())
    if isinstance(obj, list):
        return 1 + sum(count_nodes(item) for item in obj)
    return 1


def enforce_json_limits(obj: Any, raw_bytes: int, limits: JsonLimits) -> None:
    """Assert a decoded body fits ``limits``; raise otherwise (§14.2 / §14.12).

    Order of checks: raw byte size first (cheapest, no traversal), then depth,
    then node count. Raises :class:`JsonTooLarge`, :class:`JsonTooDeep` or
    :class:`ValueError` (node overflow) respectively; returns ``None`` when the
    body is within budget.
    """
    if raw_bytes > limits.max_bytes:
        raise JsonTooLarge(
            f"JSON body {raw_bytes} B exceeds max_bytes={limits.max_bytes} / "
            f"тело JSON превышает лимит байт"
        )
    depth = json_depth(obj)
    if depth > limits.max_depth:
        raise JsonTooDeep(
            f"JSON depth {depth} exceeds max_depth={limits.max_depth} / "
            f"вложенность JSON превышает лимит"
        )
    nodes = count_nodes(obj)
    if nodes > limits.max_nodes:
        raise ValueError(
            f"JSON node count {nodes} exceeds max_nodes={limits.max_nodes} / "
            f"число узлов JSON превышает лимит"
        )
