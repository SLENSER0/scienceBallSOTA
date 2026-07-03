"""Caption↔object anchoring (§5.7 / §8.3).

Pure-python linker that anchors extracted figure/table captions to the concrete
table/figure objects they describe — привязка подписей к объектам. Each caption
carries a ``kind`` (``figure``/``table``) and a parsed ``number``; each table or
figure object carries a ``number`` and a stable ``id``. :func:`link_captions`
returns one frozen :class:`CaptionLink` per input caption, in input order.

Linking rule (per caption, only objects of the SAME ``kind`` are candidates):

* exact ``number`` match → link to that object, ``confidence == 1.0``;
* otherwise, fall back to the next still-unmatched object of that kind, taken in
  input order → ``confidence == 0.5``;
* if no candidate object remains → ``target_id is None``, ``confidence == 0.0``.

A caption is a legitimate evidence source (§8.3), so a resolved link feeds the
evidence graph with the anchored object ``id``. Kuzu note: the derived link props
(``confidence``/``target_id``) are read via ``get_node()`` — they are NOT
queryable columns; RETURN base columns only. No external dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CaptionLink", "link_captions"]


@dataclass(frozen=True)
class CaptionLink:
    """One caption anchored to a table/figure object (§5.7 / §8.3).

    ``kind`` is ``"figure"`` or ``"table"``; ``number`` is the caption number;
    ``caption_text`` is the caption body; ``target_id`` is the linked object id
    (``None`` when nothing could be anchored); ``confidence`` is ``1.0`` for an
    exact number match, ``0.5`` for the order-based fallback, ``0.0`` when unlinked.
    """

    kind: str
    number: int
    caption_text: str
    target_id: str | None
    confidence: float

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict (``target_id`` may be ``None``)."""
        return {
            "kind": self.kind,
            "number": self.number,
            "caption_text": self.caption_text,
            "target_id": self.target_id,
            "confidence": self.confidence,
        }


def link_captions(
    captions: list[dict],
    tables: list[dict],
    figures: list[dict],
) -> list[CaptionLink]:
    """Anchor each caption to a table/figure object of the same kind (§5.7 / §8.3).

    ``captions`` items have ``kind`` (``"figure"``/``"table"``), ``number`` and
    ``text``; ``tables``/``figures`` items have ``number`` and ``id``. Returns one
    :class:`CaptionLink` per caption, in input order (so ``len(result) ==
    len(captions)``). Exact number match scores ``1.0``, the order fallback ``0.5``,
    and an unlinkable caption ``0.0`` with ``target_id is None``.
    """
    # Pools of still-unmatched objects per kind, preserving input order.
    pools: dict[str, list[dict]] = {
        "figure": list(figures),
        "table": list(tables),
    }
    links: list[CaptionLink] = []
    for caption in captions:
        kind = caption["kind"]
        number = int(caption["number"])
        text = caption.get("text", "")
        pool = pools.get(kind, [])
        target_id, confidence = _resolve(number, pool)
        links.append(
            CaptionLink(
                kind=kind,
                number=number,
                caption_text=text,
                target_id=target_id,
                confidence=confidence,
            )
        )
    return links


def _resolve(number: int, pool: list[dict]) -> tuple[str | None, float]:
    """Consume and return the best object for *number* from *pool* (§5.7).

    Mutates *pool*: the chosen object is removed so it cannot anchor a second
    caption. Exact number match → ``(id, 1.0)``; else the next remaining object in
    order → ``(id, 0.5)``; else ``(None, 0.0)``.
    """
    for index, obj in enumerate(pool):
        if int(obj["number"]) == number:
            return pool.pop(index)["id"], 1.0
    if pool:
        return pool.pop(0)["id"], 0.5
    return None, 0.0
