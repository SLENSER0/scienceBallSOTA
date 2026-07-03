"""Compose service lint — линтер здоровья/рестарта/лимитов сервисов (§2.5).

A production-grade Docker Compose service should declare four operational safety
nets, and their absence is a silent reliability drift:

* a ``healthcheck`` — иначе orchestrator cannot tell a hung container from a live
  one, so no restart or dependency-gate ever fires;
* a ``restart`` policy — без него a crashed process stays down until a human notices;
* CPU/memory ``deploy.resources.limits`` — an unbounded service can starve its
  neighbours (noisy-neighbour), особенно stateful stores;
* log rotation via ``logging.options.max-size`` — иначе the JSON log file grows
  until it fills the disk.

This module is deliberately I/O-free — детерминизм: the caller feeds in the parsed
service mapping and the linter emits one :class:`ServiceLintFinding` per missing net.

* :func:`lint_services` walks the mapping and yields findings sorted by
  ``(service, rule)`` — stable output for CI diffs.
* :func:`is_stateful` marks known storage services (Neo4j/Qdrant/Postgres/…), where
  resource limits matter most; it is a hint for callers, not a gate here.

:class:`ServiceLintFinding` is a frozen dataclass with ``as_dict()`` for JSON/CI
serialisation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ServiceLintFinding",
    "is_stateful",
    "lint_services",
]

# Known storage/stateful services — где лимиты ресурсов критичнее всего (§2.5).
_STATEFUL: frozenset[str] = frozenset(
    {
        "neo4j",
        "qdrant",
        "postgres",
        "postgresql",
        "redis",
        "minio",
        "elasticsearch",
        "opensearch",
        "mongo",
        "mongodb",
        "mysql",
        "mariadb",
        "clickhouse",
        "kafka",
    }
)


@dataclass(frozen=True, slots=True)
class ServiceLintFinding:
    """One lint finding for a Compose service — одна находка линтера (§2.5).

    ``service`` is the service name, ``rule`` the machine code (always ``SL_``-prefixed)
    and ``message`` a human-readable explanation. The dataclass is frozen so a produced
    finding is a stable, hashable record suitable for sets and CI diffs.
    """

    service: str
    rule: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "service": self.service,
            "rule": self.rule,
            "message": self.message,
        }


def is_stateful(name: str) -> bool:
    """Report whether ``name`` is a known storage service — стораджевый ли сервис (§2.5).

    Matching is case-insensitive. A trailing ``-1``/``_1`` compose replica index is
    stripped, so both ``neo4j`` and a scaled ``neo4j-1`` resolve to the same stateful
    class. The whole token and its last ``_``/``-`` segment are both checked, so a
    prefixed ``proj_neo4j`` still matches on ``neo4j``.
    """
    token = name.strip().lower()
    # Strip a trailing replica index ('-1' / '_1').
    for sep in ("-", "_"):
        head, found, tail = token.rpartition(sep)
        if found and tail.isdigit():
            token = head
            break
    if token in _STATEFUL:
        return True
    return any(token.rsplit(sep, 1)[-1] in _STATEFUL for sep in ("_", "-"))


def _has_healthcheck(service: Mapping[str, Any]) -> bool:
    """True iff the service declares a ``healthcheck`` — есть ли healthcheck."""
    return bool(service.get("healthcheck"))


def _has_restart(service: Mapping[str, Any]) -> bool:
    """True iff the service declares a ``restart`` policy — есть ли restart."""
    return bool(service.get("restart"))


def _has_limits(service: Mapping[str, Any]) -> bool:
    """True iff ``deploy.resources.limits`` is present — есть ли лимиты."""
    deploy = service.get("deploy")
    if not isinstance(deploy, Mapping):
        return False
    resources = deploy.get("resources")
    if not isinstance(resources, Mapping):
        return False
    return bool(resources.get("limits"))


def _has_log_rotation(service: Mapping[str, Any]) -> bool:
    """True iff ``logging.options.max-size`` is present — есть ли ротация логов."""
    logging = service.get("logging")
    if not isinstance(logging, Mapping):
        return False
    options = logging.get("options")
    if not isinstance(options, Mapping):
        return False
    return options.get("max-size") is not None


def lint_services(
    services: Mapping[str, Mapping[str, Any]],
) -> tuple[ServiceLintFinding, ...]:
    """Lint every service for operational safety nets — линт сервисов (§2.5).

    For each service emits a :class:`ServiceLintFinding` for every missing net:

    * ``SL_NO_HEALTHCHECK`` — no ``healthcheck`` key;
    * ``SL_NO_RESTART`` — no ``restart`` key;
    * ``SL_NO_LIMITS`` — no ``deploy.resources.limits``;
    * ``SL_NO_LOG_ROTATION`` — no ``logging.options.max-size``.

    The returned tuple is sorted by ``(service, rule)`` for deterministic CI output.
    """
    findings: list[ServiceLintFinding] = []
    for name, service in services.items():
        svc: Mapping[str, Any] = service if isinstance(service, Mapping) else {}
        if not _has_healthcheck(svc):
            findings.append(
                ServiceLintFinding(
                    service=name,
                    rule="SL_NO_HEALTHCHECK",
                    message=f"service '{name}' has no healthcheck",
                )
            )
        if not _has_restart(svc):
            findings.append(
                ServiceLintFinding(
                    service=name,
                    rule="SL_NO_RESTART",
                    message=f"service '{name}' has no restart policy",
                )
            )
        if not _has_limits(svc):
            findings.append(
                ServiceLintFinding(
                    service=name,
                    rule="SL_NO_LIMITS",
                    message=f"service '{name}' has no deploy.resources.limits",
                )
            )
        if not _has_log_rotation(svc):
            findings.append(
                ServiceLintFinding(
                    service=name,
                    rule="SL_NO_LOG_ROTATION",
                    message=f"service '{name}' has no logging.options.max-size",
                )
            )
    findings.sort(key=lambda f: (f.service, f.rule))
    return tuple(findings)
