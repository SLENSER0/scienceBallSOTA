"""Fulltext ``aliases_text`` assembly for synonym-aware search (§3.8/§3.12).

Многие модули читают поле ``aliases_text`` узла, но ни один канонически его не
собирает (grep по ``build_aliases_text`` пуст). §3.8/§3.12 требуют собирать это
поле на upsert, чтобы полнотекстовый индекс (*fulltext*) ловил синонимы: имя,
каноническое имя и алиасы узла сводятся в один текст, по которому идёт поиск.

Сборка (*assembly*) детерминирована: поверхностные формы (*surfaces*) берутся из
``name``, затем ``canonical_name``, затем ``aliases`` — в порядке первого
появления (*first appearance*). Пустые и состоящие лишь из пробелов записи
отбрасываются; дубликаты снимаются без учёта регистра (``str.casefold``), при этом
сохраняется первая встреченная поверхностная форма. Итоговый ``text`` — это
поверхности, склеенные разделителем ``" | "``.

Kuzu note: кастомные свойства узла (в т.ч. ``aliases_text``) НЕ являются
запрашиваемыми колонками — их читают через ``get_node()``; в ``RETURN`` идут только
базовые колонки. Поэтому :class:`AliasText` сериализуется плоским :meth:`as_dict`,
пригодным для property-map узла при upsert (§8.2).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Separator joining surfaces into the fulltext string (§3.12). Chosen so individual
# surfaces stay tokenisable and visually distinct in the assembled ``text``.
SURFACE_SEPARATOR = " | "


@dataclass(frozen=True)
class AliasText:
    """Immutable result of assembling a node's fulltext ``aliases_text`` (§3.12).

    Attributes
    ----------
    canonical:
        Canonical surface for the node — the first non-blank of ``name`` /
        ``canonical_name`` seen during assembly (``""`` if none).
    surfaces:
        Deduplicated, order-preserving tuple of surface forms.
    text:
        ``surfaces`` joined by :data:`SURFACE_SEPARATOR`; the fulltext payload.
    """

    canonical: str
    surfaces: tuple[str, ...]
    text: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.12).

        Carries ``canonical``, ``surfaces`` (as a list) and ``text`` — ready as a
        property-map fragment for the node at upsert.
        """
        return {
            "canonical": self.canonical,
            "surfaces": list(self.surfaces),
            "text": self.text,
        }


def _clean(value: str | None) -> str | None:
    """Return ``value`` stripped, or ``None`` if blank/whitespace-only (§3.12)."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def build_aliases_text(
    name: str | None,
    canonical_name: str | None,
    aliases: Sequence[str] | None,
) -> AliasText:
    """Assemble the fulltext ``aliases_text`` for a node (§3.8/§3.12).

    Collects ``name``, then ``canonical_name``, then each entry of ``aliases`` in
    order; drops blank/whitespace-only entries; dedupes case-insensitively via
    ``str.casefold`` keeping the first surface seen (original order preserved); and
    joins the survivors with :data:`SURFACE_SEPARATOR` to form ``text``.

    The ``canonical`` field is the first non-blank of ``name`` / ``canonical_name``.
    """
    candidates: list[str] = []
    for value in (name, canonical_name):
        cleaned = _clean(value)
        if cleaned is not None:
            candidates.append(cleaned)
    for alias in aliases or ():
        cleaned = _clean(alias)
        if cleaned is not None:
            candidates.append(cleaned)

    surfaces: list[str] = []
    seen: set[str] = set()
    for surface in candidates:
        folded = surface.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        surfaces.append(surface)

    canonical = candidates[0] if candidates else ""
    return AliasText(
        canonical=canonical,
        surfaces=tuple(surfaces),
        text=SURFACE_SEPARATOR.join(surfaces),
    )


def surfaces_of(node: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the assembled surfaces for a node-like mapping (§3.12).

    Reads ``name``, ``canonical_name`` and ``aliases`` from ``node`` (each optional)
    and delegates to :func:`build_aliases_text`, returning only its surfaces.
    """
    return build_aliases_text(
        node.get("name"),
        node.get("canonical_name"),
        node.get("aliases"),
    ).surfaces
