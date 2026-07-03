"""Compose profile consistency — паритет опциональных/обязательных профилей (§2.2).

A docker-compose stack splits services into two operational classes. *Optional*
services (metrics, tracing, dashboards) must sit behind a compose ``profile`` so
``docker compose up`` starts only the always-on core; *required* services (the
API, the database) must be profile-free so they come up unconditionally. When
these rules drift, an operator either cannot start an optional service (it has no
profile to activate) or accidentally gates a required one behind a profile that a
plain ``up`` never turns on.

This module is deliberately I/O-free and clock-free — детерминизм: the caller
extracts the ``service -> [profiles]`` mapping from the parsed compose file and
passes it alongside the declared optional/required service names and the set of
known profile identifiers. :func:`check_profiles` diffs the three into a frozen
:class:`ProfileReport`.

* **missing_profile** — optional services that declare *no* profile: they would
  start on every ``up`` instead of only when explicitly selected.
* **stray_profile** — required (always-on) services that declare *any* profile:
  they would be silently skipped by a plain ``up``.
* **unknown_profiles** — ``(service, profile)`` pairs whose profile is not in the
  set of known profile identifiers: a typo or an undeclared profile name.

All three are sorted; ``ok`` is true iff all three are empty.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ProfileReport",
    "check_profiles",
]


@dataclass(frozen=True, slots=True)
class ProfileReport:
    """Result of a compose profile consistency check — результат проверки (§2.2).

    ``missing_profile`` are optional services with an empty profile list (sorted).
    ``stray_profile`` are required services that declare any profile (sorted).
    ``unknown_profiles`` are ``(service, profile)`` pairs referencing an unknown
    profile (sorted by ``(service, profile)``). ``ok`` is true iff all three are
    empty.
    """

    missing_profile: tuple[str, ...]
    stray_profile: tuple[str, ...]
    unknown_profiles: tuple[tuple[str, str], ...]
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "missing_profile": list(self.missing_profile),
            "stray_profile": list(self.stray_profile),
            "unknown_profiles": [list(pair) for pair in self.unknown_profiles],
            "ok": self.ok,
        }


def check_profiles(
    service_profiles: Mapping[str, Iterable[str]],
    optional: Iterable[str],
    required: Iterable[str],
    known_profiles: Iterable[str],
) -> ProfileReport:
    """Diff optional/required services against declared profiles — сверка (§2.2).

    ``service_profiles`` maps each service to its declared profile list.
    ``optional`` services must declare at least one profile; ``required``
    services must declare none. ``known_profiles`` is the set of valid profile
    identifiers.

    Returns a :class:`ProfileReport` where:

    * ``missing_profile`` = optional services whose profile list is empty;
    * ``stray_profile`` = required services that declare any profile;
    * ``unknown_profiles`` = ``(service, profile)`` pairs whose profile is not in
      ``known_profiles``.

    All three are sorted; ``ok`` is true iff all three are empty.
    """
    optional_set = set(optional)
    required_set = set(required)
    known_set = set(known_profiles)

    missing: list[str] = []
    stray: list[str] = []
    unknown: list[tuple[str, str]] = []

    for service, raw_profiles in service_profiles.items():
        profiles = list(raw_profiles)
        if service in optional_set and not profiles:
            missing.append(service)
        if service in required_set and profiles:
            stray.append(service)
        for profile in profiles:
            if profile not in known_set:
                unknown.append((service, profile))

    return ProfileReport(
        missing_profile=tuple(sorted(missing)),
        stray_profile=tuple(sorted(stray)),
        unknown_profiles=tuple(sorted(unknown)),
        ok=not missing and not stray and not unknown,
    )
