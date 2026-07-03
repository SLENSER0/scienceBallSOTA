"""Makefile required-target coverage — проверка целей Makefile (§2.1).

A project ``Makefile`` is expected to expose a stable set of developer entry
points (``up``, ``down``, ``test`` …).  This module parses the rule names out
of Makefile text and reports which of the *required* targets are present and
which are missing, as one frozen, JSON-serialisable verdict.

Parsing rules (deterministic, side-effect free):

* A **rule** is any *non-indented* line of the form ``name:`` where ``name``
  matches ``[A-Za-z0-9._-]+`` («имя цели»).  Everything after the first colon
  (prerequisites/deps) is ignored — ``demo: up seed`` registers ``demo``.
* **Indented** lines (recipe bodies, tab- or space-prefixed) are never targets.
* **Dotted special targets** such as ``.PHONY``/``.DEFAULT`` are ignored — a
  ``.PHONY: up`` line does not register ``up`` (nor ``.PHONY``) as a target.
* Names are returned **sorted** and de-duplicated.

Public API:

* :class:`MakefileReport` — frozen verdict with :meth:`MakefileReport.as_dict`.
* :data:`DEFAULT_REQUIRED` — the §2.1 required-target set.
* :func:`parse_targets` — sorted rule names from Makefile text.
* :func:`check_required` — coverage verdict over required targets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "DEFAULT_REQUIRED",
    "MakefileReport",
    "check_required",
    "parse_targets",
]

# §2.1 — the canonical developer entry points every Makefile must expose.
DEFAULT_REQUIRED: frozenset[str] = frozenset(
    {
        "up",
        "down",
        "logs",
        "ps",
        "init-db",
        "seed",
        "backup",
        "restore",
        "test",
        "lint",
        "fmt",
    }
)

# Non-indented ``name:`` at line start; name = [A-Za-z0-9._-]+, rest is deps.
_RULE_RE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)\s*:")


@dataclass(frozen=True, slots=True)
class MakefileReport:
    """Immutable required-target verdict — результат проверки целей (§2.1).

    ``ok`` is ``True`` exactly when ``missing`` is empty.  Both tuple fields
    are sorted so the record is a pure function of its inputs.
    """

    present: tuple[str, ...]
    missing: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — сводка как словарь (§2.1)."""
        return {
            "present": list(self.present),
            "missing": list(self.missing),
            "ok": self.ok,
        }


def parse_targets(text: str) -> tuple[str, ...]:
    """Return sorted, de-duplicated rule names — имена целей (§2.1).

    Only non-indented ``name:`` lines are rules; indented recipe lines and
    dotted special targets (``.PHONY`` …) are skipped.  Prerequisites after
    the colon are ignored.
    """
    names: set[str] = set()
    for line in text.splitlines():
        if not line or line[0] in " \t":
            # Empty or indented (recipe body) — not a target line.
            continue
        match = _RULE_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        if name.startswith("."):
            # Dotted special target (.PHONY/.DEFAULT/…) — not a real target.
            continue
        names.add(name)
    return tuple(sorted(names))


def check_required(text: str, required: Iterable[str] = DEFAULT_REQUIRED) -> MakefileReport:
    """Report present/missing required targets — покрытие целей (§2.1).

    ``missing`` is the sorted set of ``required`` names absent from ``text``;
    ``present`` is the sorted set of required names found.  ``ok`` is ``True``
    exactly when ``missing`` is empty.
    """
    found = set(parse_targets(text))
    required_set = set(required)
    present = tuple(sorted(required_set & found))
    missing = tuple(sorted(required_set - found))
    return MakefileReport(present=present, missing=missing, ok=not missing)
