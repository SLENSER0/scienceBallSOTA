"""Env-var reference sync checker — синхронизация справочника переменных (§19.12).

The *env-reference-sync* gate (§19.12) guards against documentation drift for
environment variables: every ``os.environ`` / ``os.getenv`` access in the code
should be described in a hand-maintained registry, and every documented variable
should actually be read somewhere. Otherwise operators tune a variable that does
nothing, or the app quietly depends on an undocumented one.

The model is deliberately I/O-free and clock-free — детерминизм: the caller feeds
in the *source text* to scan and the declared :class:`EnvVarSpec` registry, and
this module reconciles the two name sets.

* :func:`extract_env_names` scans source for the four canonical access forms
  (``os.environ['X']``, ``os.environ.get('X')``, ``os.getenv('X')``,
  ``getenv('X')``) with single or double quotes and returns the referenced names.
* :func:`documented_names` collapses a registry of specs to their names.
* :func:`reconcile` returns a :class:`ReconcileReport` splitting the symmetric
  difference into *undocumented* (in code, not in docs) and *unused* (in docs, not
  in code); both tuples are sorted for deterministic output.

:class:`EnvVarSpec` and :class:`ReconcileReport` are frozen dataclasses with
``as_dict()`` for JSON/CI serialisation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EnvVarSpec",
    "ReconcileReport",
    "documented_names",
    "extract_env_names",
    "reconcile",
]


# Matches the four canonical env-access forms with a single- or double-quoted
# name captured in group ``name``:
#   os.environ['X'] / os.environ["X"]
#   os.environ.get('X') / os.environ.get("X")
#   os.getenv('X') / os.getenv("X")
#   getenv('X') / getenv("X")
# Только буквенно-цифровые имена — a bare string literal that is not one of these
# accessors is never captured.
_ENV_ACCESS = re.compile(
    r"""
    (?:
        os\.environ\s*\[\s*        # os.environ[
      | os\.environ\.get\s*\(\s*   # os.environ.get(
      | os\.getenv\s*\(\s*         # os.getenv(
      | (?<![\w.])getenv\s*\(\s*   # bare getenv( (not preceded by ident/dot)
    )
    (?P<q>['"])                    # opening quote
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    (?P=q)                         # matching closing quote
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class EnvVarSpec:
    """One documented environment variable — описание переменной окружения (§19.12).

    ``required`` marks a variable the app cannot start without; ``secret`` marks a
    value that must be redacted in logs/exports; ``default`` is the fallback value
    or ``None`` when there is no default.
    """

    name: str
    required: bool
    secret: bool
    default: str | None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "name": self.name,
            "required": self.required,
            "secret": self.secret,
            "default": self.default,
        }


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """Result of reconciling code vs docs — результат сверки (§19.12).

    ``undocumented`` are names read in code but absent from the registry;
    ``unused`` are documented names never read in code. Both tuples are sorted for
    deterministic output. The env-reference-sync gate passes iff both are empty.
    """

    undocumented: tuple[str, ...]
    unused: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "undocumented": list(self.undocumented),
            "unused": list(self.unused),
        }


def extract_env_names(source: str) -> frozenset[str]:
    """Extract env-var names from source — извлечь имена переменных (§19.12).

    Scans ``source`` for the four canonical access forms — ``os.environ['X']``,
    ``os.environ.get('X')``, ``os.getenv('X')`` and bare ``getenv('X')`` — with
    single or double quotes, and returns the referenced names. Plain string
    literals that are not env accessors are ignored.
    """
    return frozenset(m.group("name") for m in _ENV_ACCESS.finditer(source))


def documented_names(specs: Iterable[EnvVarSpec]) -> frozenset[str]:
    """Collect documented variable names — собрать имена из справочника (§19.12)."""
    return frozenset(spec.name for spec in specs)


def reconcile(code_names: frozenset[str], documented: frozenset[str]) -> ReconcileReport:
    """Reconcile code names against docs — сверить код со справочником (§19.12).

    ``undocumented`` = ``code_names`` minus ``documented`` (read but not
    described); ``unused`` = ``documented`` minus ``code_names`` (described but
    never read). Both tuples are sorted for deterministic output.
    """
    undocumented = tuple(sorted(code_names - documented))
    unused = tuple(sorted(documented - code_names))
    return ReconcileReport(undocumented=undocumented, unused=unused)
