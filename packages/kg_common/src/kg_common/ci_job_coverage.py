"""Required CI/CD workflow-job coverage — покрытие обязательных job'ов (§2.10/§2.4).

A CI pipeline is only trustworthy if it actually *runs* the gates the spec
mandates. §2.10 (with §2.4) fixes a floor of workflow jobs every pipeline must
carry: ``lint`` (ruff), ``test`` (pytest), ``build``, ``compose-smoke`` (bring
the stack up and probe it), ``hadolint`` (Dockerfile linting), ``trivy``
(image/filesystem vulnerability scan), and ``dr-test`` (disaster-recovery
restore rehearsal). Dropping any one of these silently weakens the release
gate — the pipeline stays green while a whole class of checks has quietly gone
missing.

This module is deliberately I/O-free and clock-free — детерминизм: the caller
passes the *observed* set of job names (e.g. parsed from a workflow YAML) and,
optionally, the *required* set (defaulting to :data:`DEFAULT_REQUIRED_JOBS`).
:func:`check_jobs` diffs the two into a frozen :class:`CIJobReport`:

* **missing** — required − present: mandated jobs the pipeline lacks (the
  failure mode).
* **extra** — present − required: jobs the pipeline runs beyond the floor
  (purely informational — a richer pipeline is fine).

``present``, ``missing`` and ``extra`` are all sorted (and ``present`` is
deduplicated). ``ok`` is true iff ``missing`` is empty; ``extra`` never affects
``ok``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CIJobReport",
    "DEFAULT_REQUIRED_JOBS",
    "check_jobs",
]

# The mandated CI/CD workflow jobs from §2.10 (with §2.4) — обязательные job'ы.
DEFAULT_REQUIRED_JOBS: frozenset[str] = frozenset(
    {
        "lint",
        "test",
        "build",
        "compose-smoke",
        "hadolint",
        "trivy",
        "dr-test",
    }
)


@dataclass(frozen=True, slots=True)
class CIJobReport:
    """Result of a CI job-coverage check — результат проверки покрытия (§2.10).

    ``present`` are the observed jobs (sorted, deduplicated). ``missing`` are
    required jobs absent from ``present`` (sorted) — the failure mode. ``extra``
    are present jobs beyond the required floor (sorted) — informational only.
    ``ok`` is true iff ``missing`` is empty.
    """

    present: tuple[str, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "present": list(self.present),
            "missing": list(self.missing),
            "extra": list(self.extra),
            "ok": self.ok,
        }


def check_jobs(
    present: Iterable[str],
    required: Iterable[str] = DEFAULT_REQUIRED_JOBS,
) -> CIJobReport:
    """Diff observed jobs against the required floor — сверка job'ов (§2.10).

    ``missing`` = required − present, ``extra`` = present − required; both
    sorted. ``present`` is sorted and deduplicated. ``ok`` is true iff
    ``missing`` is empty (``extra`` is informational and does not affect it).
    """
    present_set = set(present)
    required_set = set(required)
    missing = tuple(sorted(required_set - present_set))
    extra = tuple(sorted(present_set - required_set))
    return CIJobReport(
        present=tuple(sorted(present_set)),
        missing=missing,
        extra=extra,
        ok=not missing,
    )
