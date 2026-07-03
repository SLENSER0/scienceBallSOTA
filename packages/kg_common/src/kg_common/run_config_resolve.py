"""Run config resolution — разрешение конфигурации запуска (§9.7/§9.9).

A partitioned run starts from *defaults* and then layers *per-partition
overrides* on top. This module provides a tiny, store-free resolver that
deep-merges dict-valued keys recursively while treating scalars and lists as
whole-value replacements.

Rules:

* Scalars (``int``, ``str``, ``bool``, ``None``, ...) — the later override
  wins («последний побеждает»).
* Dicts — merged recursively, key by key.
* Lists / tuples / any non-dict value — **replaced**, never merged (a list is
  an atomic value here, «список заменяется целиком»).

The result is a :class:`ResolvedConfig`: a frozen wrapper whose
:meth:`ResolvedConfig.as_dict` hands back an *independent* deep copy, so callers
can freely mutate what they receive without corrupting the resolved state.

Public API:

* :class:`ResolvedConfig` — frozen resolved config with :meth:`as_dict`.
* :func:`resolve_config` — deep-merge defaults with overrides.
* :func:`get_path` — read a nested value by a dotted path.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ResolvedConfig",
    "get_path",
    "resolve_config",
]


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """Immutable resolved config — неизменяемая разрешённая конфигурация (§9.7).

    The wrapped :attr:`data` is treated as read-only: never mutate it in place.
    Use :meth:`as_dict` to obtain a private, mutation-safe copy.
    """

    data: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return an independent deep copy — независимая глубокая копия.

        Each call yields a fresh structure, so mutating one result never leaks
        into :attr:`data` or into any other :meth:`as_dict` call.
        """
        return copy.deepcopy(dict(self.data))


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` — рекурсивное слияние.

    Both dict-valued keys are merged key by key; every other value (scalar,
    list, tuple, ...) from ``override`` replaces the one in ``base``. ``base`` is
    mutated in place and returned.
    """
    for key, value in override.items():
        existing = base.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            base[key] = _deep_merge(existing, value)
        else:
            base[key] = copy.deepcopy(value) if isinstance(value, Mapping) else value
    return base


def resolve_config(defaults: Mapping[str, Any], *overrides: Mapping[str, Any]) -> ResolvedConfig:
    """Deep-merge ``defaults`` with successive ``overrides`` — послойное слияние.

    Later overrides win on scalars; dict-valued keys merge recursively; lists and
    other non-dict values are replaced whole. Inputs are never mutated — the
    result owns a fresh deep copy of everything.
    """
    merged: dict[str, Any] = copy.deepcopy(dict(defaults))
    for override in overrides:
        _deep_merge(merged, override)
    return ResolvedConfig(data=merged)


def get_path(cfg: ResolvedConfig, dotted: str, default: Any = None) -> Any:
    """Read a nested value by dotted path — чтение по точечному пути (§9.9).

    ``dotted`` is split on ``"."`` and each segment traverses one dict level. If
    any segment is missing or a non-dict is encountered mid-traversal, ``default``
    is returned.
    """
    current: Any = cfg.data
    for segment in dotted.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return default
        current = current[segment]
    return current
