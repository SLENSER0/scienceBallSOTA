"""Версионирование узлов — node lifecycle valid_from/valid_to/superseded_by (§16.7).

A node's history is modelled by a chain of immutable versions. Bumping a node creates a
:class:`VersionTransition` with two sides:

* ``old`` — a copy of the previous node, closed off by stamping ``valid_to=now`` and
  (when a successor id is supplied) ``superseded_by=new_id``. Its own properties are left
  untouched — the change set is applied only to the successor.
* ``new`` — the successor node: previous props + ``changes``, with ``version`` incremented,
  ``valid_from=now``, ``valid_to=None`` and ``superseded_by=None`` (a fresh open version).

Поведение / behaviour:

* ``version`` defaults to an implicit ``1`` when absent, so a first bump yields ``2``.
* :func:`is_current` reports whether a node is the open (live) version — ``valid_to is None``.

The helper is pure and backend-agnostic; callers persist ``old``/``new`` via their own
store (in Kuzu these custom props live off the base columns — read them via ``get_node``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VersionTransition:
    """Результат перехода версии — the closed ``old`` and open ``new`` node (§16.7).

    :param old: previous node, stamped with ``valid_to`` (and ``superseded_by``).
    :param new: successor node with the change set applied and a fresh open window.
    """

    old: dict[str, Any]
    new: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view — сериализуемое представление перехода."""
        return {"old": dict(self.old), "new": dict(self.new)}


def bump_version(
    node: Mapping[str, Any],
    changes: Mapping[str, Any],
    now: str,
    new_id: str | None = None,
) -> VersionTransition:
    """Close ``node`` and produce its successor version — переход версии (§16.7).

    The ``old`` side is a copy of ``node`` with ``valid_to=now`` (and ``superseded_by=new_id``
    when ``new_id`` is given); the ``new`` side applies ``changes``, increments ``version``
    (implicit ``1`` when absent), and opens a fresh window (``valid_from=now``,
    ``valid_to=None``, ``superseded_by=None``).
    """
    old: dict[str, Any] = dict(node)
    old["valid_to"] = now
    if new_id is not None:
        old["superseded_by"] = new_id

    current_version = node.get("version", 1)
    new: dict[str, Any] = dict(node)
    new.update(changes)
    new["version"] = current_version + 1
    new["valid_from"] = now
    new["valid_to"] = None
    new["superseded_by"] = None

    return VersionTransition(old=old, new=new)


def is_current(node: Mapping[str, Any]) -> bool:
    """True when ``node`` is the open (live) version — текущая версия (§16.7)."""
    return node.get("valid_to") is None
