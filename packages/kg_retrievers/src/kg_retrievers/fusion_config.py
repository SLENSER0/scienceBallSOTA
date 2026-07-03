"""Spec-exact §12.16 fusion-weights config object (pure python, no store access).

RU: Конфиг слияния каналов (§12.16). Оборачивает выбор стратегии из §12.4 —
``rrf`` (Reciprocal Rank Fusion, §7.5 Node 6) или ``weighted`` (линейная
взвешенная сумма §10.2) — вместе с весами каналов и константой ``rrf_k``.
Инвариант §12.4 «сумма весов == 1.0» проверяется ТОЛЬКО для ``weighted``
(в ``rrf`` веса не участвуют в формуле, поэтому не ограничиваются).
EN: Fusion-strategy config (§12.16). Bundles the §12.4 method switch —
``rrf`` (Reciprocal Rank Fusion, §7.5 Node 6) or ``weighted`` (§10.2 linear
weighted sum) — with the per-channel weights and the ``rrf_k`` constant.
The §12.4 «weights sum to 1.0» invariant is enforced for ``weighted`` only;
``rrf`` ignores the weights, so they are left unconstrained.

Builds ON :mod:`kg_retrievers.fusion`: reuses :data:`DEFAULT_FUSION_WEIGHTS`,
:data:`DEFAULT_RRF_K` and :func:`validate_weights` (that module is not edited).
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before assembling fusion inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_retrievers.fusion import (
    DEFAULT_FUSION_WEIGHTS,
    DEFAULT_RRF_K,
    validate_weights,
)

# §12.4 fusion strategies (config flag ``fusion.method``).
METHOD_RRF = "rrf"  # Reciprocal Rank Fusion (§7.5 Node 6)
METHOD_WEIGHTED = "weighted"  # §10.2 linear weighted sum

FUSION_METHODS: frozenset[str] = frozenset({METHOD_RRF, METHOD_WEIGHTED})


@dataclass(frozen=True)
class FusionConfig:
    """Validated fusion configuration (§12.16): method + weights + ``rrf_k``.

    ``method`` is one of :data:`METHOD_RRF` / :data:`METHOD_WEIGHTED`; ``weights``
    maps a §10.2 channel name to its weight; ``rrf_k`` is the RRF constant (>0).
    Validation runs in ``__post_init__``: unknown method or non-positive ``rrf_k``
    raise ``ValueError``; ``weighted`` additionally requires the §12.4 «sum == 1.0»
    invariant (delegated to :func:`validate_weights`). A defensive copy of
    ``weights`` is stored so the frozen instance owns its dict.
    """

    method: str = METHOD_WEIGHTED
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_FUSION_WEIGHTS))
    rrf_k: int = DEFAULT_RRF_K

    def __post_init__(self) -> None:
        if self.method not in FUSION_METHODS:
            raise ValueError(
                f"fusion method must be one of {sorted(FUSION_METHODS)}, got {self.method!r}"
            )
        if self.rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {self.rrf_k!r}")
        # Frozen dataclass: own a private copy of the caller's weights dict.
        object.__setattr__(self, "weights", dict(self.weights))
        if self.method == METHOD_WEIGHTED:
            validate_weights(self.weights)  # §12.4: weights must sum to 1.0

    def as_dict(self) -> dict:
        """Plain-dict projection for config dump / round-trip (§12.16, house style)."""
        return {
            "method": self.method,
            "weights": dict(self.weights),
            "rrf_k": self.rrf_k,
        }

    @classmethod
    def from_dict(cls, d: dict) -> FusionConfig:
        """Rebuild (and re-validate) from an :meth:`as_dict` projection (§12.16).

        Missing keys fall back to the module defaults (``weighted`` method,
        :data:`DEFAULT_FUSION_WEIGHTS`, :data:`DEFAULT_RRF_K`). Validation is the
        same as the constructor's, so a malformed dict raises ``ValueError``.
        """
        raw_weights = d.get("weights")
        weights = dict(raw_weights) if raw_weights is not None else dict(DEFAULT_FUSION_WEIGHTS)
        return cls(
            method=d.get("method", METHOD_WEIGHTED),
            weights=weights,
            rrf_k=int(d.get("rrf_k", DEFAULT_RRF_K)),
        )


def default_fusion_config() -> FusionConfig:
    """Canonical default config (§12.16): ``weighted`` over :data:`DEFAULT_FUSION_WEIGHTS`.

    Uses ``rrf_k`` = :data:`DEFAULT_RRF_K` and the §10.2 default weights (sum 1.0),
    so the returned instance is always valid.
    """
    return FusionConfig()
