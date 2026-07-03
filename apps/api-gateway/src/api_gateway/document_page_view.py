"""Document viewer — parsed page block render model (§17.19/§17.13).

Frontend-agnostic представление одной распарсенной страницы документа: набор
блоков (параграфы, таблицы, рисунки) с якорями и целью подсветки. Каждый блок
имеет стабильный ``block_id``, нормализованный ``kind``, плотный 0-based
``order``, ``anchor`` вида ``'{kind}:{block_id}'`` и флаг ``highlighted``.

A frontend-agnostic render model for one parsed document page: a tuple of blocks
(paragraphs, tables, figures) each carrying an anchor and a highlight flag. The
view sorts by the input ``order``, reassigns a dense 0-based order, normalises
``kind`` into ``{'paragraph','table','figure'}`` and marks the highlight target.

* :class:`PageBlock` — frozen render record for one page block with :meth:`as_dict`.
* :class:`PageView` — frozen page view (blocks + highlight id) with :meth:`as_dict`.
* :func:`build_page_view` — build a :class:`PageView` from raw parsed block dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Допустимые нормализованные типы блоков / allowed normalised block kinds.
_KINDS: frozenset[str] = frozenset({"paragraph", "table", "figure"})
_DEFAULT_KIND = "paragraph"


def _normalise_kind(raw: object) -> str:
    """Нормализовать тип блока; неизвестное → ``'paragraph'`` (§17.19).

    Lower-case ``raw`` and keep it only if it is one of ``{'paragraph','table',
    'figure'}``; anything else (including ``None``) falls back to ``'paragraph'``.
    """
    kind = str(raw).strip().lower()
    return kind if kind in _KINDS else _DEFAULT_KIND


@dataclass(frozen=True, slots=True)
class PageBlock:
    """Неизменяемый блок страницы для рендера (§17.19).

    Immutable render record for a single parsed page block. ``anchor`` is the
    ``'{kind}:{block_id}'`` handle a frontend scrolls to; ``highlighted`` is true
    only for the block whose id equals the view's highlight target.
    """

    block_id: str
    kind: str
    order: int
    text: str
    anchor: str
    highlighted: bool

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в camelCase dict (``blockId`` и т.д.) (§17.19).

        Serialise to a JSON-ready camelCase ``dict`` with exactly six keys.
        """
        return {
            "blockId": self.block_id,
            "kind": self.kind,
            "order": self.order,
            "text": self.text,
            "anchor": self.anchor,
            "highlighted": self.highlighted,
        }


@dataclass(frozen=True, slots=True)
class PageView:
    """Неизменяемое представление одной страницы документа (§17.19).

    Immutable render model for one document page: an ordered tuple of
    :class:`PageBlock` plus the optional ``highlight_id`` currently targeted.
    """

    doc_id: str
    page: int
    blocks: tuple[PageBlock, ...]
    highlight_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в camelCase dict (``docId``/``highlightId``) (§17.19).

        Serialise to a JSON-ready camelCase ``dict``; ``highlightId`` round-trips
        ``None`` unchanged and ``blocks`` becomes a list of block dicts.
        """
        return {
            "docId": self.doc_id,
            "page": self.page,
            "blocks": [block.as_dict() for block in self.blocks],
            "highlightId": self.highlight_id,
        }


def build_page_view(
    doc_id: str,
    page: int,
    parsed_blocks: list[dict],
    *,
    highlight_id: str | None = None,
) -> PageView:
    """Собрать :class:`PageView` из сырых распарсенных блоков (§17.19/§17.13).

    Sort ``parsed_blocks`` by their input ``order``, then rebuild each into a
    :class:`PageBlock` with a dense 0-based ``order``, a normalised ``kind``, an
    ``anchor`` of ``'{kind}:{block_id}'`` and ``highlighted`` true iff its
    ``block_id`` equals ``highlight_id``.
    """
    ordered = sorted(parsed_blocks, key=lambda raw: raw.get("order", 0))
    blocks: list[PageBlock] = []
    for dense, raw in enumerate(ordered):
        block_id = str(raw["block_id"])
        kind = _normalise_kind(raw.get("kind"))
        blocks.append(
            PageBlock(
                block_id=block_id,
                kind=kind,
                order=dense,
                text=str(raw.get("text", "")),
                anchor=f"{kind}:{block_id}",
                highlighted=block_id == highlight_id,
            )
        )
    return PageView(doc_id=doc_id, page=page, blocks=tuple(blocks), highlight_id=highlight_id)
