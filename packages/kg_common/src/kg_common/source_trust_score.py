"""Composite source-trust score & tier — доверие к источнику (§23.27).

``source_freshness`` (§10.7) only classifies *staleness*, and ``retractions``
only *stores* whether a source was retracted; neither yields a single number
that answers «насколько можно доверять этому источнику?». This module folds four
signals into one aggregate ``0..1`` trust score plus a coarse tier label:

* **freshness** — exponential decay ``0.5 ** (age_days / half_life_days)``: a
  brand-new source scores ``1.0``, one exactly a half-life old scores ``0.5``;
* **retraction** — a retracted source is *untrusted* outright: score ``0.0``,
  tier ``'untrusted'``, no matter how fresh or well-cited it is;
* **peer review** — a boolean bonus; peer-reviewed sources outrank identical
  non-reviewed ones («рецензирование поднимает доверие»);
* **citations** — a saturating pull ``count / (count + 10)``: ``0`` citations
  contribute ``0.0``, ``10`` contribute ``0.5``, and the effect asymptotes.

The three live components are averaged with fixed weights, clamped to ``[0, 1]``
and bucketed into tiers: ``low`` (``< 0.34``), ``medium`` (``< 0.67``) and
``high`` (``>= 0.67``). A retracted source short-circuits to ``untrusted``.

Public API:

* :data:`TIERS`       — the tier labels in worsening order.
* :class:`TrustScore` — frozen verdict with :meth:`TrustScore.as_dict`.
* :func:`score_source` — build a :class:`TrustScore` from raw signals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

__all__ = [
    "TIERS",
    "TrustScore",
    "score_source",
]

#: Tier labels от «высокого» доверия к «отсутствию» (§23.27).
TIERS: tuple[str, ...] = ("high", "medium", "low", "untrusted")

#: Tier boundaries on the score — границы бакетов (§23.27).
_LOW_MAX: float = 0.34
_MEDIUM_MAX: float = 0.67

#: Citation half-saturation constant — count//(count+K) → 0.5 at count==K.
_CITATION_K: float = 10.0

#: Peer-review component value when the flag is set / unset — вклад рецензии.
_PEER_YES: float = 1.0
_PEER_NO: float = 0.0

#: Component weights (must sum to 1.0) — веса компонентов агрегата.
_W_FRESHNESS: float = 0.4
_W_CITATION: float = 0.4
_W_PEER: float = 0.2


@dataclass(frozen=True, slots=True)
class TrustScore:
    """Immutable trust verdict for one source — вердикт доверия (§23.27).

    ``source_id`` identifies the source; ``score`` is the aggregate trust in
    ``[0, 1]``; ``tier`` is one of :data:`TIERS`; ``retracted`` mirrors the
    retraction flag that (when set) forced ``score`` to ``0.0``; ``components``
    maps each named signal (``freshness``/``citation``/``peer_review``) to its
    own ``0..1`` contribution before weighting. A plain frozen value so it can
    be hashed, compared and serialized.
    """

    source_id: str
    score: float
    tier: str
    retracted: bool
    components: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        """Return a plain ``dict`` copy — сериализуемое представление (§23.27)."""
        return asdict(self)


def _tier_for(score: float) -> str:
    """Bucket a ``0..1`` score into a tier label — раскладка по бакетам (§23.27)."""
    if score < _LOW_MAX:
        return "low"
    if score < _MEDIUM_MAX:
        return "medium"
    return "high"


def score_source(
    source_id: str,
    age_days: float,
    retracted: bool,
    peer_reviewed: bool,
    citation_count: int,
    half_life_days: float = 1825.0,
) -> TrustScore:
    """Combine freshness, retraction, peer review & citations into a trust score.

    ``age_days`` is the source's age in days (``0`` == brand-new); ``retracted``
    short-circuits the verdict to ``untrusted``; ``peer_reviewed`` grants a
    bonus component; ``citation_count`` feeds the saturating citation pull;
    ``half_life_days`` sets how fast freshness decays (default ``1825`` == 5y).

    Returns a :class:`TrustScore`. Raises :class:`ValueError` on negative
    ``age_days`` («возраст не может быть отрицательным»).
    """
    if age_days < 0:
        raise ValueError("age_days must be non-negative — возраст не может быть < 0")

    freshness = 0.5 ** (age_days / half_life_days)
    count = max(0, citation_count)
    citation = count / (count + _CITATION_K)
    peer = _PEER_YES if peer_reviewed else _PEER_NO
    components = {
        "freshness": freshness,
        "citation": citation,
        "peer_review": peer,
    }

    if retracted:
        return TrustScore(
            source_id=source_id,
            score=0.0,
            tier="untrusted",
            retracted=True,
            components=components,
        )

    raw = _W_FRESHNESS * freshness + _W_CITATION * citation + _W_PEER * peer
    score = min(1.0, max(0.0, raw))
    return TrustScore(
        source_id=source_id,
        score=score,
        tier=_tier_for(score),
        retracted=False,
        components=components,
    )
