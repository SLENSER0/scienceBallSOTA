"""Trust-weighted answer-support eval (§23.27).

Флагует ответы, опирающиеся на отозванные/малодоверенные источники. В отличие
от ``source_trust_score`` (оценивает один источник) и ``claim_support`` (сверка
чисел), здесь на вход подаётся per-claim разметка, а на выходе — взвешенное по
доверию покрытие и предупреждение, если отозванное/заменённое evidence служит
первичной опорой (§23.27: retracted evidence не должно быть первичным источником
без предупреждения).

Flags answers that lean on retracted/low-trust sources. Distinct from
``source_trust_score`` (scores one source) and ``claim_support`` (number match):
input is per-claim support with source status and trust; output is a
trust-weighted support score plus a warning when a retracted/superseded source is
relied upon.

Pure-python: только stdlib, детерминированно / stdlib only, deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from statistics import fmean

# Статусы источника, которые никогда не считаются опорой (§23.27).
# Source statuses that never count as support.
_NEVER_SUPPORT = frozenset({"retracted", "superseded"})

# Допустимые статусы источника / valid source statuses.
_VALID_STATUS = frozenset({"active", "corrected", "retracted", "superseded"})


@dataclass(frozen=True)
class ClaimTrust:
    """Итог по одному claim: доверие-взвешенная опора и признак опоры на отзыв.

    Per-claim outcome: trust-weighted effective support and whether the claim
    relies on a retracted/superseded source (RU/EN).
    """

    id: str
    effective_support: float
    retracted_reliant: bool

    def as_dict(self) -> dict[str, object]:
        """Return the claim outcome as a plain dict (RU: как словарь)."""
        return {
            "id": self.id,
            "effective_support": round(float(self.effective_support), 6),
            "retracted_reliant": bool(self.retracted_reliant),
        }


@dataclass(frozen=True)
class TrustSupportReport:
    """Замороженный отчёт trust-weighted support (§23.27) — RU/EN."""

    n: int
    weighted_support: float
    retracted_reliant_ids: tuple[str, ...]
    warning: bool

    def as_dict(self) -> dict[str, object]:
        """Return the report as plain floats + sorted ids (RU: как словарь)."""
        return {
            "n": int(self.n),
            "weighted_support": round(float(self.weighted_support), 6),
            "retracted_reliant_ids": list(self.retracted_reliant_ids),
            "warning": bool(self.warning),
        }


def _score_one(claim: Mapping[str, object]) -> ClaimTrust:
    """Оценить один claim → :class:`ClaimTrust` (RU: оценка одного claim)."""
    cid = str(claim["id"])
    supported = bool(claim["supported"])
    status = str(claim["source_status"])
    trust = float(claim["trust"])

    if status not in _VALID_STATUS:
        raise ValueError(f"unknown source_status: {status!r}")
    if not 0.0 <= trust <= 1.0:
        raise ValueError(f"trust must be in [0, 1], got {trust!r}")

    never = status in _NEVER_SUPPORT
    # Отозванное/заменённое evidence никогда не засчитывается как опора.
    effective_support = trust if (supported and not never) else 0.0
    retracted_reliant = supported and never

    return ClaimTrust(
        id=cid,
        effective_support=effective_support,
        retracted_reliant=retracted_reliant,
    )


def score_support(claims: Iterable[Mapping[str, object]]) -> TrustSupportReport:
    """Посчитать trust-weighted support по per-claim разметке (§23.27).

    Для каждого claim ``effective_support = trust`` если ``supported`` и статус не
    ``retracted``/``superseded``; иначе ``0.0``. ``weighted_support`` — среднее
    ``effective_support`` по всем claims. ``warning`` истинно, если хотя бы один
    claim опирается на отозванный/заменённый источник. Пустой вход → ValueError.

    Computes trust-weighted support from per-claim rows. Raises ``ValueError`` on
    empty input.
    """
    scored = [_score_one(claim) for claim in claims]
    if not scored:
        raise ValueError("score_support requires at least one claim")

    weighted_support = fmean(c.effective_support for c in scored)
    reliant_ids = tuple(sorted(c.id for c in scored if c.retracted_reliant))

    return TrustSupportReport(
        n=len(scored),
        weighted_support=weighted_support,
        retracted_reliant_ids=reliant_ids,
        warning=bool(reliant_ids),
    )
