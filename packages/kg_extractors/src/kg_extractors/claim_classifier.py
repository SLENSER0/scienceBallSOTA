"""Rule-based ``claim_type`` / ``polarity`` classifier (§6.9).

Правило-ориентированный классификатор типа утверждения и полярности.

``ClaimExtract.claim_type`` is normally set by the LLM during schema-guided
extraction (§6.9). That is the accurate path but also the expensive one, and it
leaves nothing to *check the model against*. This module supplies the missing
deterministic fallback: a cue-word classifier that maps a claim sentence to a
coarse ``claim_type`` + ``polarity`` with zero model calls — cheap enough to run
on every claim and useful as a review signal when the LLM label disagrees.

Taxonomy (§6.9):

- ``claim_type`` ∈ ``{finding, recommendation, limitation, comparison}``
- ``polarity``   ∈ ``{recommended, not_recommended, neutral}``

Rules, applied in priority order (first match wins so a negated recommendation
is never mistaken for a plain one):

1. ``should not`` / ``avoid`` → ``recommendation`` + ``not_recommended``
2. ``recommend`` / ``should`` → ``recommendation`` + ``recommended``
3. ``limited to`` / ``however`` / ``could not`` → ``limitation`` + ``neutral``
4. ``higher than`` / ``compared to`` / ``outperforms`` → ``comparison`` + ``neutral``
5. otherwise → ``finding`` + ``neutral``

The matched cue surfaces are preserved on :attr:`ClaimClass.cues` for review /
explainability. Matching is case-insensitive and substring-based (RU + EN).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Allowed vocabularies (§6.9). Kept as frozensets so callers can validate.
CLAIM_TYPES: frozenset[str] = frozenset({"finding", "recommendation", "limitation", "comparison"})
POLARITIES: frozenset[str] = frozenset({"recommended", "not_recommended", "neutral"})

# Cue surfaces per rule, checked in the order below (RU stems + EN words). The
# negated-recommendation cues must precede the plain ones so «should not» wins
# over «should». Порядок правил важен: отрицание проверяется первым.
_NOT_RECOMMENDED_CUES: tuple[str, ...] = (
    "should not",
    "must not",
    "avoid",
    "do not",
    "не следует",
    "не рекомендуется",
    "избегать",
)
_RECOMMENDED_CUES: tuple[str, ...] = (
    "recommend",
    "should",
    "advised",
    "preferred",
    "рекомендуется",
    "следует",
)
_LIMITATION_CUES: tuple[str, ...] = (
    "limited to",
    "however",
    "could not",
    "limitation",
    "cannot",
    "ограничен",
    "однако",
)
_COMPARISON_CUES: tuple[str, ...] = (
    "higher than",
    "compared to",
    "outperforms",
    "outperform",
    "greater than",
    "lower than",
    "versus",
    "higher",
    "than",
    "выше чем",
    "по сравнению",
)


@dataclass(frozen=True)
class ClaimClass:
    """Immutable classification result for a single claim sentence (§6.9).

    Неизменяемый результат классификации утверждения.
    """

    claim_type: str
    polarity: str
    cues: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError(f"unknown claim_type: {self.claim_type!r}")
        if self.polarity not in POLARITIES:
            raise ValueError(f"unknown polarity: {self.polarity!r}")

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain ``dict`` (``claim_type`` / ``polarity`` / ``cues``)."""
        return asdict(self)


def _matched(text: str, cues: tuple[str, ...]) -> tuple[str, ...]:
    """Return the cue surfaces present in *text* (case-insensitive), in cue order."""
    low = text.lower()
    return tuple(cue for cue in cues if cue in low)


def classify_claim(text: str) -> ClaimClass:
    """Classify a claim sentence into ``claim_type`` + ``polarity`` by cue words (§6.9).

    Классифицирует утверждение по ключевым словам. First matching rule wins.
    """
    negated = _matched(text, _NOT_RECOMMENDED_CUES)
    if negated:
        return ClaimClass("recommendation", "not_recommended", negated)

    recommended = _matched(text, _RECOMMENDED_CUES)
    if recommended:
        return ClaimClass("recommendation", "recommended", recommended)

    limitation = _matched(text, _LIMITATION_CUES)
    if limitation:
        return ClaimClass("limitation", "neutral", limitation)

    comparison = _matched(text, _COMPARISON_CUES)
    if comparison:
        return ClaimClass("comparison", "neutral", comparison)

    return ClaimClass("finding", "neutral", ())
