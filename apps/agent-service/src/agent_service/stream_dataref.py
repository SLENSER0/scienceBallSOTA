"""§13.22 streaming progress (SSE) — ``dataRef`` pointers / указатели на данные.

§13.22 streams progress events over SSE. Bulky tool outputs (graph, table, evidence, gaps)
are *not* inlined into the stream; instead the stream carries a stable, deterministic
``dataRef`` pointer that the UI later resolves against the full payload. This module mints
those pointers.

Pure-python and deterministic: nothing here touches the graph store, so the module stays
unit-testable without a seeded Kuzu database (свойства узлов Kuzu не являются колонками
запроса / node props are not queryable columns — irrelevant here, no store access).

Surface:

* :class:`DataRef` — frozen ``(ref, kind, size)`` pointer with :meth:`~DataRef.as_dict`.
* :func:`make_dataref` — build a :class:`DataRef` from a ``kind`` and a payload.
* :func:`is_bulky` — True when a payload is large enough to warrant a pointer.
* :func:`same_ref` — True iff two :class:`DataRef` share an identical ``ref`` string.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Kinds that may be referenced by pointer / допустимые виды указателей.
_ALLOWED_KINDS: frozenset[str] = frozenset({"graph", "table", "evidence", "gaps"})

# Default bulk threshold / порог объёмности по умолчанию.
_DEFAULT_THRESHOLD: int = 20


@dataclass(frozen=True)
class DataRef:
    """A stable pointer to a bulky tool output / устойчивый указатель на объёмный вывод.

    ``ref`` is ``f"{kind}:{sha1(canonical_json(payload))[:12]}"``; ``kind`` is one of
    ``{'graph', 'table', 'evidence', 'gaps'}``; ``size`` is the element count of the payload.
    """

    ref: str
    kind: str
    size: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe projection / JSON-совместимая проекция ``{'ref', 'kind', 'size'}``."""
        return {"ref": self.ref, "kind": self.kind, "size": self.size}


def _canonical_json(payload: Any) -> str:
    """Deterministic JSON / детерминированный JSON with sorted keys and no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _payload_size(payload: Any) -> int:
    """Element count / число элементов: ``len`` for list/dict, else ``1``."""
    if isinstance(payload, (list, dict)):
        return len(payload)
    return 1


def make_dataref(kind: str, payload: Any) -> DataRef:
    """Mint a deterministic :class:`DataRef` / отчеканить детерминированный указатель.

    ``kind`` must be in ``{'graph', 'table', 'evidence', 'gaps'}`` (иначе ValueError / else
    ValueError). ``ref`` hashes the sorted-key canonical JSON of ``payload`` so identical
    ``kind`` + ``payload`` always yield the same ``ref``.
    """
    if kind not in _ALLOWED_KINDS:
        allowed = ", ".join(sorted(_ALLOWED_KINDS))
        raise ValueError(f"unknown dataRef kind {kind!r}; expected one of {allowed}")
    digest = hashlib.sha1(_canonical_json(payload).encode("utf-8")).hexdigest()[:12]
    return DataRef(ref=f"{kind}:{digest}", kind=kind, size=_payload_size(payload))


def is_bulky(payload: Any, threshold: int = _DEFAULT_THRESHOLD) -> bool:
    """True when ``len(payload) > threshold`` / объёмен ли payload.

    Payloads without a length (scalars) are never bulky (скаляр не объёмен / a scalar has
    no length, so it is treated as small).
    """
    try:
        return len(payload) > threshold
    except TypeError:
        return False


def same_ref(a: DataRef, b: DataRef) -> bool:
    """True iff two :class:`DataRef` share the same ``ref`` / совпадают ли указатели."""
    return a.ref == b.ref
