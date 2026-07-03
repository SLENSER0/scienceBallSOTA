"""Feature-flag parity checker — проверка паритета фич-флагов (§23.19).

The *feature-flags-parity* CI gate (§23.19) guards against silent configuration
drift: a feature flag that is switched on in ``prod`` but off in ``dev`` (or vice
versa) is a latent surprise, and a flag enabled *anywhere* that nobody declared
in the flag registry is an undocumented toggle. Nothing else in the repo checks
this, so this module is the single source of truth for "are our environments in
parity?".

The model is deliberately tiny and clock-free — детерминизм: no I/O, no globals.
The caller supplies

* a ``registry`` — the set of every flag name that is *allowed* to exist, and
* ``env_flags`` — a mapping of environment name → the set of flags **enabled** in
  that environment.

A flag is treated as *disabled* in an environment simply by being absent from
that environment's enabled-set. :func:`check` then reports two independent kinds
of trouble:

* **Divergence** — a flag that is enabled in at least one environment and
  disabled in at least one other. Uniformly-on and uniformly-off flags are in
  parity and never reported.
* **Unknown flags** — flags enabled in some environment that do not appear in the
  registry. These are undocumented toggles regardless of parity.

:class:`FlagDivergence` and :class:`ParityReport` are frozen dataclasses with
``as_dict()`` for JSON/CI serialisation. ``in_parity`` is true iff there are no
divergences *and* no unknown flags.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Any

__all__ = [
    "FlagDivergence",
    "ParityReport",
    "check",
]


@dataclass(frozen=True, slots=True)
class FlagDivergence:
    """One flag that disagrees across environments — расхождение флага (§23.19).

    ``enabled_in`` lists the environments where the flag is on, ``disabled_in``
    the environments where it is off. Both tuples are sorted by environment name
    and, for a genuine divergence, both are non-empty.
    """

    flag: str
    enabled_in: tuple[str, ...]
    disabled_in: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "flag": self.flag,
            "enabled_in": list(self.enabled_in),
            "disabled_in": list(self.disabled_in),
        }


@dataclass(frozen=True, slots=True)
class ParityReport:
    """Result of a parity check — результат проверки паритета (§23.19).

    ``environments`` are the checked environments (sorted). ``unknown_flags`` are
    enabled flags absent from the registry (sorted, deduplicated). ``divergent``
    holds one :class:`FlagDivergence` per drifting flag (sorted by flag name).
    ``in_parity`` is true iff both ``unknown_flags`` and ``divergent`` are empty.
    """

    environments: tuple[str, ...]
    unknown_flags: tuple[str, ...]
    divergent: tuple[FlagDivergence, ...]
    in_parity: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "environments": list(self.environments),
            "unknown_flags": list(self.unknown_flags),
            "divergent": [d.as_dict() for d in self.divergent],
            "in_parity": self.in_parity,
        }


def check(registry: Set[str], env_flags: Mapping[str, Set[str]]) -> ParityReport:
    """Check flag parity across environments — проверить паритет флагов (§23.19).

    A flag is *divergent* when it is enabled in at least one environment and
    disabled (absent) in at least one other. ``unknown_flags`` are the enabled
    flags not present in ``registry`` (sorted, deduplicated across environments).
    ``in_parity`` is true iff there are no divergences and no unknown flags.
    """
    environments = tuple(sorted(env_flags))

    # Every flag that is enabled in at least one environment.
    all_enabled: set[str] = set()
    for flags in env_flags.values():
        all_enabled |= set(flags)

    unknown_flags = tuple(sorted(flag for flag in all_enabled if flag not in registry))

    divergences: list[FlagDivergence] = []
    for flag in all_enabled:
        enabled_in = tuple(env for env in environments if flag in env_flags[env])
        disabled_in = tuple(env for env in environments if flag not in env_flags[env])
        if enabled_in and disabled_in:
            divergences.append(
                FlagDivergence(flag=flag, enabled_in=enabled_in, disabled_in=disabled_in)
            )

    divergent = tuple(sorted(divergences, key=lambda d: d.flag))
    in_parity = not divergent and not unknown_flags

    return ParityReport(
        environments=environments,
        unknown_flags=unknown_flags,
        divergent=divergent,
        in_parity=in_parity,
    )
