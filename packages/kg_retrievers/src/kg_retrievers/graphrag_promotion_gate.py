"""GraphRAG build promotion gate — alias-swap eligibility (§11.10 / §11.13).

Decides whether a freshly-built GraphRAG index may be *promoted* to active by an
alias swap. Per §11.10 the alias is switched **only after successful validation**
(«переключать alias только после успешной валидации»); §11.13 adds the answer-quality
bars. This module combines *structural integrity* with Mode-C answer-quality
thresholds into one build-specific decision that lists concrete blockers.

Врата продвижения сборки GraphRAG: alias переключается только после успешной
валидации (§11.10) и при выполнении порогов качества (§11.13). Здесь структурная
целостность объединяется с порогами качества ответов режима Mode-C, а решение
перечисляет конкретные блокеры.

Note: ``kg_eval.quality_gates`` is a *generic* higher-is-better metric gate; this
module is the GraphRAG-build-specific promotion decision naming concrete blockers.
Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Blocker tags, appended in a fixed order (integrity → claims → citations).
_BLOCKER_INTEGRITY: str = "integrity_failed"
_BLOCKER_UNSUPPORTED: str = "unsupported_claims"
_BLOCKER_CITATION: str = "low_citation_precision"


@dataclass(frozen=True)
class PromotionDecision:
    """Verdict on promoting a freshly-built GraphRAG index (§11.10 / §11.13).

    - ``promote`` — whether the alias swap is allowed (True iff no blockers);
    - ``blockers`` — ordered tuple of failure tags, e.g. ``integrity_failed`` /
      ``unsupported_claims`` / ``low_citation_precision``.

    Решение о продвижении сборки: ``promote`` истинно только при пустом наборе
    ``blockers``.
    """

    promote: bool
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a plain-dict view (``promote`` stays a ``bool``)."""
        return asdict(self)


def evaluate_promotion(
    integrity_ok: bool,
    unsupported_claim_rate: float,
    citation_precision: float,
    max_unsupported: float = 0.0,
    min_citation_precision: float = 0.8,
) -> PromotionDecision:
    """Decide alias-swap eligibility for a GraphRAG build (§11.10 / §11.13).

    Args:
        integrity_ok: whether structural-integrity checks passed for the build.
        unsupported_claim_rate: fraction of answer claims without support.
        citation_precision: precision of emitted citations in ``[0, 1]``.
        max_unsupported: highest tolerated unsupported-claim rate (default ``0.0``).
        min_citation_precision: lowest tolerated citation precision (default ``0.8``).

    Blockers are appended in a fixed order:
        1. ``integrity_failed`` when ``not integrity_ok``;
        2. ``unsupported_claims`` when ``unsupported_claim_rate > max_unsupported``;
        3. ``low_citation_precision`` when ``citation_precision < min_citation_precision``.

    Promotion is allowed iff no blockers were recorded.

    Врата продвижения: alias можно переключать только при пустом списке блокеров.
    """
    blockers: list[str] = []
    if not integrity_ok:
        blockers.append(_BLOCKER_INTEGRITY)
    if unsupported_claim_rate > max_unsupported:
        blockers.append(_BLOCKER_UNSUPPORTED)
    if citation_precision < min_citation_precision:
        blockers.append(_BLOCKER_CITATION)
    return PromotionDecision(promote=not blockers, blockers=tuple(blockers))
