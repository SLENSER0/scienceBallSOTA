"""Spec §12.4/§12.5 fusion-weight redistribution when a component is unavailable.

RU: Перераспределение весов слияния (§12.5 «вес перераспределяется согласно
config-политике», когда в Mode A отсутствует ``graph_proximity``; §12.4 dedup —
отсутствующие компоненты считаются равными 0). Ни один текущий модуль не
ренормирует «выпавшие» веса, поэтому эта чистая (без доступа к store) утилита
отбрасывает недоступные ключи и масштабирует оставшиеся так, чтобы их сумма
снова равнялась 1.0, СОХРАНЯЯ их относительные пропорции.
EN: Fusion-weight redistribution (§12.5 «weight is redistributed per config
policy» when Mode A lacks ``graph_proximity``; §12.4 dedup treats missing
components as 0). No module renormalizes dropped fusion weights today, so this
pure (no store access) helper drops the unavailable keys and rescales the rest
to sum back to 1.0 while PRESERVING their relative proportions.

Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before assembling fusion inputs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedistributedWeights:
    """Result of §12.4/§12.5 redistribution: surviving ``weights`` + ``dropped`` keys.

    ``weights`` maps each surviving §10.2 channel to its rescaled weight (summing
    to 1.0 unless every key was dropped, giving an empty dict); ``dropped`` is the
    sorted tuple of keys removed because they were not in ``available``.
    """

    weights: dict[str, float]
    dropped: tuple[str, ...]

    def as_dict(self) -> dict:
        """Plain-dict projection for trace / round-trip (§12.4, house style)."""
        return {
            "weights": dict(self.weights),
            "dropped": tuple(self.dropped),
        }


def redistribute(weights: dict[str, float], available: set[str]) -> RedistributedWeights:
    """Drop unavailable channels and rescale the rest to sum 1.0 (§12.4/§12.5).

    RU: Удаляет ключи, отсутствующие в ``available``, затем делит каждый
    оставшийся вес на сумму оставшихся — пропорции сохраняются, сумма == 1.0.
    Если оставшихся весов нет (или их сумма == 0), возвращаются пустые веса.
    EN: Removes keys not in ``available``, then divides every surviving weight by
    the surviving total — relative proportions are preserved and the sum is 1.0.
    If nothing survives (or the survivors sum to 0), the weights are empty.
    """
    dropped = tuple(sorted(k for k in weights if k not in available))
    surviving = {k: v for k, v in weights.items() if k in available}
    total = sum(surviving.values())
    if total == 0:
        return RedistributedWeights(weights={}, dropped=dropped)
    rescaled = {k: v / total for k, v in surviving.items()}
    return RedistributedWeights(weights=rescaled, dropped=dropped)


def is_normalized(weights: dict[str, float], *, tol: float = 1e-9) -> bool:
    """True iff non-empty ``weights`` sum to 1.0 within ``tol`` (§12.4 invariant).

    An empty mapping is NOT normalized (nothing sums to 1.0), matching the §12.5
    «all components dropped» degenerate case.
    """
    if not weights:
        return False
    return abs(sum(weights.values()) - 1.0) <= tol
