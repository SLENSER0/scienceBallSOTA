"""Compose volume/network reference validator — сверка ссылок на тома/сети (§2.5).

Docker Compose services *reference* named volumes and networks (``neo4j-data:/data``),
while the top-level ``volumes:`` / ``networks:`` blocks *declare* them. If a service
references a name that is never declared, Compose fails at run time; if a name is
declared but never referenced, it is dead configuration. Обе ситуации — дрейф.

This module is deliberately I/O-free — детерминизм: the caller feeds in the parsed
service mapping and the declared name set, and the checker reconciles the two.

* :func:`referenced_volumes` collects named volumes from each service's ``volumes``
  list. An entry of the form ``name:/path`` contributes ``name``; a bind mount whose
  source starts with ``.`` or ``/`` (``./src:/app``, ``/host:/c``) is excluded.
* :func:`check_refs` splits the difference into *undeclared* (referenced, not
  declared) and *unused* (declared, not referenced); both tuples are sorted. The gate
  passes iff ``undeclared`` is empty — an unused declaration is a warning, not a
  failure.

:class:`ResourceRefReport` is a frozen dataclass with ``as_dict()`` for JSON/CI
serialisation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ResourceRefReport",
    "check_refs",
    "referenced_volumes",
]


@dataclass(frozen=True, slots=True)
class ResourceRefReport:
    """Result of a volume/network reference check — результат сверки ссылок (§2.5).

    ``undeclared`` are names referenced by a service but absent from the top-level
    declaration block; ``unused`` are declared names never referenced. Both tuples
    are sorted for deterministic output. ``ok`` is ``True`` iff ``undeclared`` is
    empty — a missing reference breaks Compose, whereas an unused declaration is only
    a warning (dead config), so it does not fail the gate.
    """

    undeclared: tuple[str, ...]
    unused: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "undeclared": list(self.undeclared),
            "unused": list(self.unused),
            "ok": self.ok,
        }


def referenced_volumes(services: Mapping[str, Mapping[str, Any]]) -> frozenset[str]:
    """Collect named volumes referenced by services — собрать имена томов (§2.5).

    For each service in ``services`` scans its ``volumes`` list; an entry of the form
    ``name:/container/path`` contributes ``name``. Bind mounts — entries whose source
    (the part before the first ``:``) starts with ``.`` or ``/`` — are excluded, as
    they map a host path rather than a named volume. Entries with no ``:`` (an
    anonymous ``/data`` volume mount) contribute nothing.
    """
    names: set[str] = set()
    for service in services.values():
        for entry in service.get("volumes", ()):  # type: ignore[union-attr]
            source, sep, _rest = str(entry).partition(":")
            if not sep:
                continue  # no ':' — anonymous volume, no name to reference
            if source.startswith((".", "/")):
                continue  # bind mount — host path, not a named volume
            if source:
                names.add(source)
    return frozenset(names)


def check_refs(referenced: Iterable[str], declared: Iterable[str]) -> ResourceRefReport:
    """Reconcile referenced names against declarations — сверить ссылки (§2.5).

    ``undeclared`` = ``referenced`` minus ``declared`` (used but not declared, which
    breaks Compose); ``unused`` = ``declared`` minus ``referenced`` (declared but
    never used, dead config). Both tuples are sorted for deterministic output. The
    report is ``ok`` iff ``undeclared`` is empty — unused declarations are warnings.
    """
    referenced_set = frozenset(referenced)
    declared_set = frozenset(declared)
    undeclared = tuple(sorted(referenced_set - declared_set))
    unused = tuple(sorted(declared_set - referenced_set))
    return ResourceRefReport(undeclared=undeclared, unused=unused, ok=not undeclared)
