"""Docker Compose port matrix — карта портов и коллизии (§2.4).

The full Compose stack (§2.4) publishes many host ports (API, Qdrant, Redis,
Grafana, …). When two services accidentally bind the *same* host port the stack
fails to start with an opaque ``address already in use``. Эта модуль разбирает
Compose-строки портов в явную матрицу и заранее находит коллизии, чтобы CI мог
провалиться с понятным сообщением ещё до ``docker compose up``.

Compose port strings understood here:

* ``"8000:8000"`` — ``host:container`` (host published, mapped to container).
* ``"6333"``       — a lone token means ``host == container`` (short syntax).
* ``"3000:80"``    — remap: host ``3000`` → container ``80``.

Public API:

* :class:`PortBinding`     — frozen ``{service, host_port, container_port}`` + ``as_dict``.
* :class:`PortMatrixReport` — frozen ``{bindings, collisions, ok}`` + ``as_dict``.
* :func:`parse_ports`      — Compose spec → sorted tuple of bindings.
* :func:`check_collisions` — group host ports bound by >1 distinct service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "PortBinding",
    "PortMatrixReport",
    "check_collisions",
    "parse_ports",
]


@dataclass(frozen=True, slots=True)
class PortBinding:
    """Один опубликованный порт — service + host/container ports (§2.4)."""

    service: str
    host_port: int
    container_port: int

    def as_dict(self) -> dict[str, object]:
        """Сериализуемое представление — JSON-friendly dict."""
        return {
            "service": self.service,
            "host_port": self.host_port,
            "container_port": self.container_port,
        }


@dataclass(frozen=True, slots=True)
class PortMatrixReport:
    """Отчёт матрицы портов — bindings + collisions + ok-флаг (§2.4)."""

    bindings: tuple[PortBinding, ...]
    collisions: tuple[tuple[int, tuple[str, ...]], ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """Сериализуемое представление — JSON-friendly dict."""
        return {
            "bindings": [b.as_dict() for b in self.bindings],
            "collisions": [
                {"host_port": port, "services": list(services)}
                for port, services in self.collisions
            ],
            "ok": bool(self.ok),
        }


def _parse_token(service: str, token: str) -> PortBinding:
    """Разобрать одну Compose-строку порта в :class:`PortBinding`.

    A lone token (``"6333"``) means ``host == container``; ``"host:container"``
    splits into the two ports.
    """
    text = token.strip()
    if ":" in text:
        host_str, container_str = text.split(":", 1)
        host_port = int(host_str.strip())
        container_port = int(container_str.strip())
    else:
        host_port = container_port = int(text)
    return PortBinding(service=service, host_port=host_port, container_port=container_port)


def parse_ports(spec: Mapping[str, Iterable[str]]) -> tuple[PortBinding, ...]:
    """Разобрать Compose-карту ``{service: [port_strings]}`` в отсортированные bindings.

    Sorted ascending by ``(host_port, container_port, service)`` for stable output.
    """
    bindings: list[PortBinding] = []
    for service, tokens in spec.items():
        for token in tokens:
            bindings.append(_parse_token(service, token))
    bindings.sort(key=lambda b: (b.host_port, b.container_port, b.service))
    return tuple(bindings)


def check_collisions(bindings: Iterable[PortBinding]) -> PortMatrixReport:
    """Найти host-порты, занятые более чем одним *различным* сервисом (§2.4).

    Collisions are grouped as ``(host_port, (service, …))`` and sorted ascending by
    host port; ``ok`` is ``True`` iff no collision exists.
    """
    materialized = tuple(bindings)
    by_port: dict[int, list[str]] = {}
    for binding in materialized:
        services = by_port.setdefault(binding.host_port, [])
        if binding.service not in services:
            services.append(binding.service)

    collisions = tuple(
        (port, tuple(sorted(services)))
        for port, services in sorted(by_port.items())
        if len(services) > 1
    )
    return PortMatrixReport(bindings=materialized, collisions=collisions, ok=not collisions)
