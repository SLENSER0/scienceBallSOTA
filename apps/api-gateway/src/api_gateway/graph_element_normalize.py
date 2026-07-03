"""Нормализация узлов/рёбер графа под §5.3 для эндпоинтов графа (§14.6).

§14.6 требует, чтобы любые графовые ответы (`GET /graph`, `POST /graph/diff`,
подграфы) соответствовали контракту §5.3: `GraphNode.type` берётся из строгого
белого списка, а `GraphNode` / `GraphEdge` несут ровно фиксированный набор полей.
Раньше отдельного нормализатора не существовало — каждый роутер собирал форму
вручную. Модуль на чистом stdlib приводит «сырой» словарь узла/ребра к wire-форме,
проваливаясь с :class:`ValueError` на отсутствующем `id` (у ребра ещё `source` /
`target`) или на типе узла вне :data:`NODE_TYPES`; булевы/целые/дробные поля
коэрсятся из истинностных значений.

Node/edge normalizer enforcing the §5.3 contract for the §14.6 graph endpoints
(`GET /graph`, `POST /graph/diff`, subgraphs): `GraphNode.type` must come from a
strict whitelist and each node/edge must carry exactly the fixed field set. No
shared normalizer existed before — every router shaped the payload by hand. Pure
stdlib: coerces a raw node/edge mapping into its wire form, raising
:class:`ValueError` on a missing `id` (edges also on missing `source` / `target`)
or a node type outside :data:`NODE_TYPES`; boolean / int / float fields are
coerced from truthy inputs.

* :data:`NODE_TYPES` — белый список типов узлов / node type whitelist.
* :class:`GraphNode` / :class:`GraphEdge` — неизменяемые записи с :meth:`as_dict`.
* :func:`normalize_node` / :func:`normalize_edge` — привести сырой словарь.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

#: Разрешённые значения ``GraphNode.type`` (§5.3) / allowed ``GraphNode.type``.
NODE_TYPES: frozenset[str] = frozenset(
    {
        "Material",
        "Experiment",
        "ProcessingRegime",
        "Property",
        "Equipment",
        "Paper",
        "Claim",
        "Lab",
        "Person",
        "Gap",
    }
)


def _as_float(value: Any, default: float = 0.0) -> float:
    """Коэрсия в float с запасным значением / coerce to float with fallback.

    ``None`` and unparsable inputs fall back to ``default``; booleans map to
    ``1.0`` / ``0.0`` so a truthy flag never leaks a non-numeric confidence.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    """Коэрсия в int с запасным значением / coerce to int with fallback.

    ``None`` yields ``default``; booleans and numeric strings coerce through
    ``int`` so ``True`` → ``1`` and ``"3"`` → ``3``. Unparsable inputs fall back.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _require(raw: Mapping[str, Any], key: str) -> Any:
    """Достать обязательное непустое поле или упасть / require a present field.

    Raises :class:`ValueError` when ``key`` is absent or maps to ``None``.
    """
    if key not in raw or raw[key] is None:
        raise ValueError(f"graph element missing required field {key!r}")
    return raw[key]


def _evidence_ids(value: Any) -> list[str]:
    """Нормализовать список идентификаторов улик / normalize evidence id list.

    ``None`` becomes ``[]``. A single scalar is wrapped into a one-item list;
    any iterable (excluding strings/bytes) is materialized with items stringified.
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value.decode() if isinstance(value, bytes) else value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


@dataclass(frozen=True, slots=True)
class GraphNode:
    """Неизменяемый узел графа по контракту §5.3 / immutable §5.3 graph node.

    Carries exactly the six wire fields. :meth:`as_dict` yields them in the
    canonical key order ``id,label,type,confidence,evidenceCount,verified``.
    """

    id: str
    label: str
    type: str
    confidence: float
    evidence_count: int
    verified: bool

    def as_dict(self) -> dict[str, Any]:
        """Wire-форма узла (ровно 6 ключей) / node wire form (exactly 6 keys)."""
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "confidence": self.confidence,
            "evidenceCount": self.evidence_count,
            "verified": self.verified,
        }


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Неизменяемое ребро графа по контракту §5.3 / immutable §5.3 graph edge.

    Carries exactly ten wire fields. :meth:`as_dict` yields them in the canonical
    order ``id,source,target,label,type,confidence,evidenceCount,inferred,
    contradicted,evidenceIds``.
    """

    id: str
    source: str
    target: str
    label: str
    type: str
    confidence: float
    evidence_count: int
    inferred: bool
    contradicted: bool
    evidence_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Wire-форма ребра (ровно 10 ключей) / edge wire form (exactly 10 keys)."""
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "type": self.type,
            "confidence": self.confidence,
            "evidenceCount": self.evidence_count,
            "inferred": self.inferred,
            "contradicted": self.contradicted,
            "evidenceIds": list(self.evidence_ids),
        }


def normalize_node(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Привести сырой узел к §5.3 wire-форме / normalize a raw node to §5.3 form.

    Returns exactly ``{id,label,type,confidence,evidenceCount,verified}``.
    ``label`` defaults to the stringified ``id`` when absent; ``confidence`` to
    ``0.0``, ``evidenceCount`` to ``0`` and ``verified`` to ``False``. Booleans /
    ints / floats are coerced from truthy inputs.

    :raises ValueError: если нет ``id`` или ``type`` вне :data:`NODE_TYPES` /
        when ``id`` is missing or ``type`` is outside :data:`NODE_TYPES`.
    """
    node_id = str(_require(raw, "id"))
    node_type = str(_require(raw, "type"))
    if node_type not in NODE_TYPES:
        raise ValueError(f"GraphNode.type {node_type!r} not in §5.3 whitelist")
    label_raw = raw.get("label")
    label = node_id if label_raw is None else str(label_raw)
    return GraphNode(
        id=node_id,
        label=label,
        type=node_type,
        confidence=_as_float(raw.get("confidence")),
        evidence_count=_as_int(raw.get("evidenceCount")),
        verified=bool(raw.get("verified")),
    ).as_dict()


def normalize_edge(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Привести сырое ребро к §5.3 wire-форме / normalize a raw edge to §5.3 form.

    Returns exactly ``{id,source,target,label,type,confidence,evidenceCount,
    inferred,contradicted,evidenceIds}``. ``label`` / ``type`` default to empty
    strings, ``confidence`` to ``0.0``, ``evidenceCount`` to ``0``, ``inferred`` /
    ``contradicted`` to ``False`` and ``evidenceIds`` to ``[]``; a list of
    evidence ids is preserved (items stringified).

    :raises ValueError: если нет ``id`` / ``source`` / ``target`` / when any of
        ``id``, ``source`` or ``target`` is missing.
    """
    edge_id = str(_require(raw, "id"))
    source = str(_require(raw, "source"))
    target = str(_require(raw, "target"))
    label_raw = raw.get("label")
    type_raw = raw.get("type")
    return GraphEdge(
        id=edge_id,
        source=source,
        target=target,
        label="" if label_raw is None else str(label_raw),
        type="" if type_raw is None else str(type_raw),
        confidence=_as_float(raw.get("confidence")),
        evidence_count=_as_int(raw.get("evidenceCount")),
        inferred=bool(raw.get("inferred")),
        contradicted=bool(raw.get("contradicted")),
        evidence_ids=_evidence_ids(raw.get("evidenceIds")),
    ).as_dict()
