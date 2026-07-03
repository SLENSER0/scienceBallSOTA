"""Sensor specifications — спецификации сенсоров (§9.9).

A *sensor* watches for an external condition and, when that condition holds,
tells a scheduler «пора запускать» (time to run). This module defines the
declarative shape of a sensor and a pure, deterministic trigger predicate — no
orchestrator dependency, no wall-clock, no filesystem access.

Three sensor *kinds* («виды») are supported:

* ``file``     — fire when a new file appears versus the last seen marker;
* ``interval`` — fire when enough time has elapsed since the last run;
* ``db``       — fire when a database cursor/marker has advanced.

Determinism (§9.9 «детерминизм»): :func:`should_trigger` never reads the clock
or the filesystem. The caller passes an explicit ``state`` mapping describing
what the outside world currently looks like (the newest file token, the current
time tick, the current db cursor) alongside the sensor's own last-seen marker.
The predicate is a pure function of ``(spec, state)``.

Public API:

* :data:`KINDS`      — the three canonical sensor kinds in canonical order.
* :class:`SensorSpec` — frozen ``(name, kind, config, enabled)`` record with
  :meth:`SensorSpec.as_dict` / :meth:`SensorSpec.from_dict`.
* :func:`should_trigger` — pure ``(spec, state) -> bool`` trigger predicate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

__all__ = [
    "KINDS",
    "SensorSpec",
    "should_trigger",
]

#: Canonical sensor kinds in canonical order — канонические виды сенсоров (§9.9).
KINDS: tuple[str, ...] = ("file", "interval", "db")


@dataclass(frozen=True, slots=True)
class SensorSpec:
    """Immutable sensor declaration — декларация сенсора (§9.9).

    ``name`` is a stable human-facing identifier; ``kind`` is one of
    :data:`KINDS`; ``config`` is a free-form per-kind settings mapping (stored as
    a read-only copy so the frozen record stays hashable-by-contract and cannot
    be mutated through the caller's original dict); ``enabled`` gates the sensor
    entirely — a disabled sensor never triggers regardless of ``state``.
    """

    name: str
    kind: str
    config: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind: {self.kind!r} (expected one of {KINDS})")
        # Freeze config into a read-only snapshot so callers cannot mutate it.
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view — таблица «имя + вид + конфиг + флаг» (§9.9)."""
        return {
            "name": self.name,
            "kind": self.kind,
            "config": dict(self.config),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SensorSpec:
        """Rebuild a :class:`SensorSpec` from :meth:`as_dict` output — из словаря (§9.9)."""
        raw_config = data.get("config", {})
        return cls(
            name=str(data["name"]),
            kind=str(data["kind"]),
            config=dict(raw_config),
            enabled=bool(data.get("enabled", True)),
        )


def should_trigger(spec: SensorSpec, state: Mapping[str, Any]) -> bool:
    """Return whether ``spec`` should fire given explicit ``state`` — сработать ли (§9.9).

    Pure and deterministic: no clock, no filesystem. ``state`` describes the
    outside world for the sensor's kind:

    * ``file``     — ``state["latest"]`` is the newest file token; the sensor
      fires when it differs from ``spec.config["last_seen"]`` (a new file
      appeared). A missing/empty ``latest`` never fires.
    * ``interval`` — ``state["now"]`` is the current tick and
      ``spec.config["last_run"]`` the previous run tick; fires when
      ``now - last_run >= config["interval"]`` (elapsed enough). Ticks are
      numbers in the same unit as ``interval``.
    * ``db``       — ``state["cursor"]`` is the current db marker; fires when it
      is greater than ``spec.config["last_cursor"]`` (the source advanced).

    A disabled sensor (``spec.enabled is False``) always returns ``False``. An
    unknown kind raises :class:`ValueError` (defensive — construction already
    validates, but ``kind`` is echoed here for clarity).
    """
    if not spec.enabled:
        return False

    config = spec.config
    if spec.kind == "file":
        latest = state.get("latest")
        if not latest:
            return False
        return latest != config.get("last_seen")

    if spec.kind == "interval":
        now = state.get("now")
        if now is None:
            return False
        last_run = config.get("last_run", 0)
        interval = config.get("interval", 0)
        return (now - last_run) >= interval

    if spec.kind == "db":
        cursor = state.get("cursor")
        if cursor is None:
            return False
        return cursor > config.get("last_cursor", 0)

    raise ValueError(f"unknown kind: {spec.kind!r} (expected one of {KINDS})")
