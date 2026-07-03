"""Domain UI badge/chip descriptors for tables & lists (§17.5).

The list/table surfaces render each entity row with a small set of *badge*
primitives (значки-бейджи) that summarise its quality signals at a glance:

* **EntityTypeChip** — the node's ``type`` (тип сущности);
* **ConfidenceBadge** — a coarse confidence bucket high/medium/low (уверенность);
* **VerifiedLock** — a lock shown only for verified nodes (проверено);
* **EvidenceCountBadge** — how many evidence links back the node (доказательства);
* **WarningBanner** — a missing-fields warning shown only when gaps exist (пропуски).

``graph_visual_style`` covers only graph-canvas node/edge styling, not these
list/table primitives, so this module owns them. It provides immutable
:class:`Badge` / :class:`BadgeSet` descriptors and :func:`build_badges`, a pure
function over a plain node dict — no store, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger

_log = get_logger("entity_badge_descriptor")

# Confidence bucket thresholds (§17.5). / Пороги ведёрок уверенности.
_HIGH_MIN = 0.8
_MEDIUM_MIN = 0.5


@dataclass(frozen=True)
class Badge:
    """One rendered badge/chip primitive. / Один бейдж-примитив.

    ``label`` is the visible text, ``tone`` the semantic colour bucket, and
    ``icon`` the icon name the UI resolves to a glyph.
    """

    label: str
    tone: str
    icon: str

    def as_dict(self) -> dict:
        return {"label": self.label, "tone": self.tone, "icon": self.icon}


@dataclass(frozen=True)
class BadgeSet:
    """The full badge set for one entity row (§17.5). / Набор бейджей строки.

    ``verified_lock`` and ``missing_warning`` are ``None`` when not applicable —
    an unverified node has no lock, a complete node has no warning banner.
    """

    type_chip: Badge
    confidence_badge: Badge
    verified_lock: Badge | None
    evidence_badge: Badge
    missing_warning: Badge | None

    def as_dict(self) -> dict:
        return {
            "typeChip": self.type_chip.as_dict(),
            "confidenceBadge": self.confidence_badge.as_dict(),
            "verifiedLock": self.verified_lock.as_dict() if self.verified_lock else None,
            "evidenceBadge": self.evidence_badge.as_dict(),
            "missingWarning": self.missing_warning.as_dict() if self.missing_warning else None,
        }


def _confidence_tone(confidence: float) -> str:
    """Bucket a confidence score into high/medium/low (§17.5). / Ведёрко уверенности."""
    if confidence >= _HIGH_MIN:
        return "high"
    if confidence >= _MEDIUM_MIN:
        return "medium"
    return "low"


def build_badges(node: dict) -> BadgeSet:
    """Build the :class:`BadgeSet` for one entity node (§17.5). / Собрать бейджи узла.

    Аргументы / Arguments:
        node: a plain node dict; read keys are ``type``, ``confidence``,
            ``verified``, ``evidenceCount`` and ``missingFields``.

    Rules / Правила:
        * confidence tone: high ``>= 0.8`` / medium ``>= 0.5`` / low ``< 0.5``;
        * ``verified_lock`` present only when ``node['verified']`` is truthy;
        * ``missing_warning`` present only when ``node['missingFields']`` is
          non-empty, with ``label`` = the count of missing fields;
        * ``evidence_badge`` label = ``str(evidenceCount)``.
    """
    entity_type = str(node.get("type", ""))
    type_chip = Badge(label=entity_type, tone="type", icon="tag")

    confidence = float(node.get("confidence", 0.0))
    tone = _confidence_tone(confidence)
    confidence_badge = Badge(label=tone, tone=tone, icon="gauge")

    verified_lock: Badge | None = None
    if node.get("verified"):
        verified_lock = Badge(label="Verified", tone="verified", icon="lock")

    evidence_count = node.get("evidenceCount", 0)
    evidence_badge = Badge(label=str(evidence_count), tone="evidence", icon="link")

    missing_warning: Badge | None = None
    missing_fields = node.get("missingFields") or []
    if missing_fields:
        missing_warning = Badge(label=str(len(missing_fields)), tone="warning", icon="alert")

    return BadgeSet(
        type_chip=type_chip,
        confidence_badge=confidence_badge,
        verified_lock=verified_lock,
        evidence_badge=evidence_badge,
        missing_warning=missing_warning,
    )
