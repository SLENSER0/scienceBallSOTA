"""Claim → about-target linking for schema-guided extraction (§6.9).

Привязка утверждения к целевым сущностям (материал/свойство/режим).

§6.9 requires each extracted claim to carry mention references
``about_material`` / ``about_property`` / ``about_regime`` naming *what* the
claim is about. :mod:`kg_extractors.entity_linking` maps mentions to canonical
node ids, but it is scope-blind: it never decides *which* mention a given claim
targets. This module closes that gap deterministically — no LLM call, no regex.

Given a claim character span ``(start, end)`` and a flat list of typed mentions
(``material`` / ``property`` / ``regime``), :func:`link_claim_targets` picks, per
target type, the mention *nearest* to the claim span. Distance is measured from
the claim span to the nearest edge of the mention (0 when they overlap); ties are
broken by the earliest ``char_start``. The chosen mention's ``text`` populates the
corresponding field; absent types stay ``None``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

# §6.9 target types. Порядок соответствует полям ClaimLink.
_TARGET_TYPES = ("material", "property", "regime")


@dataclass(frozen=True)
class ClaimLink:
    """A claim's resolved about-targets (§6.9).

    Each field holds the ``text`` of the nearest mention of that type, or
    ``None`` when no such mention exists. Ссылки утверждения на цели.
    """

    about_material: str | None
    about_property: str | None
    about_regime: str | None

    def as_dict(self) -> dict[str, str | None]:
        """Return a plain ``{field: text|None}`` mapping. Сериализация в dict."""
        return asdict(self)


def _edge_distance(claim_span: tuple[int, int], mention: Mapping[str, object]) -> int:
    """Char-distance from ``claim_span`` to the nearest edge of ``mention``.

    Returns 0 when the ranges touch or overlap. Расстояние до ближайшего края.
    """
    claim_start, claim_end = claim_span
    m_start = int(mention["char_start"])  # type: ignore[arg-type]
    m_end = int(mention["char_end"])  # type: ignore[arg-type]
    if m_end < claim_start:  # mention entirely to the left of the claim
        return claim_start - m_end
    if m_start > claim_end:  # mention entirely to the right of the claim
        return m_start - claim_end
    return 0  # overlapping / adjacent


def link_claim_targets(
    claim_span: tuple[int, int],
    mentions: list[Mapping[str, object]],
) -> ClaimLink:
    """Resolve a claim's ``about_*`` targets by nearest typed mention (§6.9).

    For each target type in {material, property, regime} pick the mention whose
    nearest edge is closest to ``claim_span``; ties break to the earliest
    ``char_start``. Missing types yield ``None``. Каждая цель — ближайшее упоминание.
    """
    best: dict[str, str | None] = dict.fromkeys(_TARGET_TYPES)
    best_key: dict[str, tuple[int, int]] = {}
    for mention in mentions:
        m_type = str(mention["type"])
        if m_type not in best:
            continue  # ignore unknown mention types
        key = (_edge_distance(claim_span, mention), int(mention["char_start"]))  # type: ignore[arg-type]
        if m_type not in best_key or key < best_key[m_type]:
            best_key[m_type] = key
            best[m_type] = str(mention["text"])
    return ClaimLink(
        about_material=best["material"],
        about_property=best["property"],
        about_regime=best["regime"],
    )
