"""GraphRAG community-report export to JSON / Markdown (§11.15).

Builds *on top of* the §11.5 / §9.8 community payload schema
(:mod:`kg_retrievers.community_payload`): it takes already-assembled
:class:`~kg_retrievers.community_payload.CommunityReportPayload` records and makes
them *portable* — a JSON array a downstream tool can round-trip, or a human-readable
Markdown (маркдаун) card a curator can read, with the community's title, summary,
key findings (выводы) and member entities (сущности).

Pure python (stdlib :mod:`json` only): no graph/store access, no LLM, no clock. The
payloads are the single source of truth; this module only reuses their
:meth:`~kg_retrievers.community_payload.CommunityReportPayload.as_dict` /
:meth:`~kg_retrievers.community_payload.CommunityReportPayload.from_dict`, so the JSON
export round-trips losslessly and both renderers are deterministic for a given input.

Entry points:

- :func:`communities_to_json` — a JSON array of §9.8 payload dicts (RU verbatim);
- :func:`communities_from_json` — parse that array back into payloads (round-trip);
- :func:`community_to_markdown` — one Markdown card (title / summary / findings /
  entities) for a single payload;
- :func:`communities_to_markdown` — one Markdown document for many payloads;
- :func:`build_community_export` — bundle payloads into a :class:`CommunityExport`.

Kuzu note: custom payload props (level, rank, findings, …) are *not* queryable
columns — a caller reading a community from the store must ``RETURN`` base columns and
hydrate the rest via ``get_node`` before assembling the payloads handed here (that is
exactly what :func:`kg_retrievers.community_payload.build_payload` already does).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from kg_retrievers.community_payload import CommunityReportPayload

# Markdown section headings (§11.15) — stable strings so renders are hand-checkable.
_H_FINDINGS = "## Findings"
_H_ENTITIES = "## Entities"

# Placeholder for an empty summary / findings / entities block: the section header is
# always emitted (so the card shape is stable), with this marker in place of content.
_EMPTY = "_None_"


def communities_to_json(
    payloads: Sequence[CommunityReportPayload], *, indent: int | None = None
) -> str:
    """Export ``payloads`` as a JSON array of §9.8 payload dicts (§11.15).

    Each element is the payload's :meth:`CommunityReportPayload.as_dict` mapping, in
    §9.8 key order; ``ensure_ascii=False`` keeps RU text (кириллица) verbatim.
    ``json.loads(communities_to_json(ps)) == [p.as_dict() for p in ps]`` for
    JSON-native field values, so the export round-trips losslessly (see
    :func:`communities_from_json`). ``indent`` is forwarded to :func:`json.dumps`
    (``None`` → compact); either way the key order is fixed, so output is deterministic.
    """
    return json.dumps(
        [p.as_dict() for p in payloads],
        ensure_ascii=False,
        indent=indent,
        default=str,
    )


def communities_from_json(text: str) -> list[CommunityReportPayload]:
    """Parse a :func:`communities_to_json` document back into payloads (§11.15).

    Reuses :meth:`CommunityReportPayload.from_dict` per element, so
    ``communities_from_json(communities_to_json(ps)) == list(ps)`` for JSON-native
    values. Raises :class:`ValueError` if the top-level JSON is not an array.
    """
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("communities_from_json expects a JSON array of payloads")
    return [CommunityReportPayload.from_dict(item) for item in data]


def _bullets(items: Sequence[str]) -> list[str]:
    """Render ``items`` as Markdown ``- `` bullets, or the empty placeholder."""
    if not items:
        return [_EMPTY]
    return [f"- {item}" for item in items]


def community_to_markdown(payload: CommunityReportPayload) -> str:
    """Render one community payload as a Markdown card (§11.15).

    Layout (always in this order, one trailing newline):

    - an ``# `` title heading — the payload ``title``, or ``Community {id}`` when it
      is blank, so the card is always identifiable;
    - a summary paragraph (or :data:`_EMPTY` when blank);
    - a :data:`_H_FINDINGS` section listing each finding (вывод) as a bullet;
    - a :data:`_H_ENTITIES` section listing each member entity id as a bullet.

    Empty findings/entities still emit their heading followed by :data:`_EMPTY`, so the
    card shape is stable. Deterministic: no clock, no sorting — input order is kept.
    """
    title = payload.title.strip() or f"Community {payload.community_id}"
    summary = payload.summary.strip() or _EMPTY
    lines: list[str] = [f"# {title}", "", summary, "", _H_FINDINGS, ""]
    lines.extend(_bullets(payload.findings))
    lines.extend(["", _H_ENTITIES, ""])
    lines.extend(_bullets(payload.entity_ids))
    return "\n".join(lines) + "\n"


def communities_to_markdown(payloads: Sequence[CommunityReportPayload]) -> str:
    """Render many payloads as one Markdown document — one card per payload (§11.15).

    Cards are joined in input order by a ``---`` horizontal rule; an empty sequence
    yields an empty string. Deterministic for a given input order.
    """
    cards = [community_to_markdown(p) for p in payloads]
    return "\n---\n\n".join(cards)


@dataclass(frozen=True)
class CommunityExport:
    """A portable bundle of community payloads, JSON/Markdown-renderable (§11.15)."""

    payloads: tuple[CommunityReportPayload, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict: ``{"communities": [<§9.8 dict>, ...]}``."""
        return {"communities": [p.as_dict() for p in self.payloads]}

    def to_json(self, *, indent: int | None = None) -> str:
        """This bundle's payloads as a JSON array (RU preserved verbatim)."""
        return communities_to_json(self.payloads, indent=indent)

    def to_markdown(self) -> str:
        """This bundle as one Markdown document — one card per payload."""
        return communities_to_markdown(self.payloads)


def build_community_export(payloads: Sequence[CommunityReportPayload]) -> CommunityExport:
    """Bundle ``payloads`` (input order preserved) into a :class:`CommunityExport`."""
    return CommunityExport(payloads=tuple(payloads))
