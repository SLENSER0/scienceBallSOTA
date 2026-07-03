"""Per-``NodeLabel`` Neo4j ``MERGE`` template generator (§3.8).

Существующий ``graph_store.py`` эмитит обобщённый Kuzu-``MERGE`` по метке ``:Node``;
§3.8 требует *метка-специфичных* Neo4j-шаблонов ``MERGE`` с разделением
``ON CREATE`` / ``ON MATCH`` и защитой рецензируемых полей. Этот модуль (*module*) —
чистый генератор строк Cypher поверх декларативной схемы: он ничего не исполняет,
а лишь рендерит идемпотентные шаблоны, пригодные для записи в Neo4j.

Правила рендеринга (§3.8):

* узел мёрджится по детерминированному ключу ``{id:$id}`` — сам ``id`` пишется
  только через ключ и никогда не входит в ``SET``;
* ``ON CREATE SET`` пишет все переданные поля (включая рецензируемые слоты —
  их надо инициализировать при первом создании);
* ``ON MATCH SET`` исключает *protected* поля (:data:`PROTECTED_FIELDS`) и
  *create-only* поля (:data:`CREATE_ONLY_FIELDS`) — их нельзя молча
  перезаписывать по повторному мёрджу;
* ребро мёрджится по ключу ``{extractor_run_id:$extractor_run_id}`` (идемпотентно
  на прогон экстрактора) и валидируется против :data:`EDGE_SCHEMA` через
  :func:`is_valid_edge` (виртуальная метка ``Entity`` разворачивается).

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их
читают через ``get_node()``. Этот модуль лишь строит текст Cypher по именам полей
и не зависит от того, как хранилище физически материализует свойства.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from kg_schema.edge_provenance import EDGE_PROVENANCE_PROPS
from kg_schema.labels import NodeLabel
from kg_schema.merge_field_policy import CREATE_ONLY_FIELDS, PROTECTED_FIELDS
from kg_schema.relationships import is_valid_edge

# Детерминированный ключ идентичности узла (§3.8) — пишется только через MERGE-ключ.
_ID_FIELD: str = "id"

# Ключ идемпотентности ребра: одно ребро на прогон экстрактора (§3.7/§3.8).
_EDGE_KEY_PROP: str = "extractor_run_id"

# Поля, которые нельзя обновлять по ON MATCH (protected + create-only) (§3.8).
_ON_MATCH_EXCLUDED: frozenset[str] = frozenset(PROTECTED_FIELDS) | frozenset(CREATE_ONLY_FIELDS)

# Дефолтный набор свойств узла для шаблона (§3.8) — база для меток без специфики.
_DEFAULT_NODE_FIELDS: tuple[str, ...] = ("name", "created_at", "created_by", "updated_at")

# Метка-специфичные наборы полей. Measurement несёт рецензируемые слоты (§3.7/§3.8).
NODE_FIELDS: dict[str, tuple[str, ...]] = {
    NodeLabel.MEASUREMENT: (
        "value",
        "value_normalized",
        "effect_direction",
        "review_status",
        "unit",
        "created_at",
        "created_by",
        "updated_at",
    ),
}


@dataclass(frozen=True)
class MergeTemplate:
    """Immutable rendered ``MERGE`` template for one node label (§3.8).

    Attributes
    ----------
    label:
        Метка узла (*node label*), например ``"Material"``.
    cypher:
        Готовый текст Cypher: ``MERGE (n:Label {id:$id}) ON CREATE SET ...
        ON MATCH SET ...``.
    on_create_fields:
        Поля, записываемые по ``ON CREATE`` (все переданные, кроме ``id``).
    on_match_fields:
        Поля, записываемые по ``ON MATCH`` (без protected / create-only полей).
    """

    label: str
    cypher: str
    on_create_fields: tuple[str, ...]
    on_match_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.8)."""
        return {
            "label": self.label,
            "cypher": self.cypher,
            "on_create_fields": list(self.on_create_fields),
            "on_match_fields": list(self.on_match_fields),
        }


def _dedupe(fields: Sequence[str]) -> tuple[str, ...]:
    """Return ``fields`` with duplicates removed, preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for field in fields:
        if field not in seen:
            seen.add(field)
            ordered.append(field)
    return tuple(ordered)


def _render_set(var: str, fields: Sequence[str]) -> str:
    """Render ``a.f = $f, ...`` for ``fields`` bound to node/rel var ``var`` (§3.8).

    Пустой набор → безопасное самоприсваивание ключа (``a.id = a.id``): держит
    предложение ``SET`` синтаксически валидным без побочных изменений.
    """
    if not fields:
        return f"{var}.{_ID_FIELD} = {var}.{_ID_FIELD}"
    return ", ".join(f"{var}.{field} = ${field}" for field in fields)


def node_merge_cypher(label: str, fields: Sequence[str]) -> MergeTemplate:
    """Render a per-label node ``MERGE`` template (§3.8).

    Узел мёрджится по ключу ``{id:$id}``. ``on_create_fields`` — все ``fields``
    без ``id``; ``on_match_fields`` дополнительно исключает *protected* и
    *create-only* поля (:data:`_ON_MATCH_EXCLUDED`), чтобы повторный мёрдж не
    затирал рецензируемые фактические слоты и поля происхождения.
    """
    on_create = _dedupe([f for f in fields if f != _ID_FIELD])
    on_match = tuple(f for f in on_create if f not in _ON_MATCH_EXCLUDED)
    cypher = (
        f"MERGE (n:{label} {{{_ID_FIELD}:${_ID_FIELD}}})\n"
        f"ON CREATE SET {_render_set('n', on_create)}\n"
        f"ON MATCH SET {_render_set('n', on_match)}"
    )
    return MergeTemplate(
        label=label,
        cypher=cypher,
        on_create_fields=on_create,
        on_match_fields=on_match,
    )


def edge_merge_cypher(
    from_label: str,
    rel: str,
    to_label: str,
    props: Sequence[str],
) -> str:
    """Render an idempotent edge ``MERGE`` (§3.7/§3.8) or raise on bad signature.

    Тройка ``(from_label, rel, to_label)`` проверяется против
    :data:`EDGE_SCHEMA` через :func:`is_valid_edge` (виртуальная метка ``Entity``
    разворачивается в :data:`ENTITY_LABELS`); недопустимая тройка → ``ValueError``.

    Ребро мёрджится по ключу ``{extractor_run_id:$extractor_run_id}``. По
    ``ON CREATE`` пишутся ``props`` плюс провенанс-свойства (кроме ключа); по
    ``ON MATCH`` — только ``props`` (не затирая ``created_at`` / ``schema_version``).
    """
    if not is_valid_edge(from_label, rel, to_label):
        raise ValueError(
            f"edge signature not in EDGE_SCHEMA: ({from_label!r}, {rel!r}, {to_label!r})"
        )
    prov_create = [p for p in EDGE_PROVENANCE_PROPS if p != _EDGE_KEY_PROP]
    on_create = _dedupe([*props, *prov_create])
    on_match = _dedupe(props)
    return (
        f"MATCH (a:{from_label} {{{_ID_FIELD}:$from_id}})\n"
        f"MATCH (b:{to_label} {{{_ID_FIELD}:$to_id}})\n"
        f"MERGE (a)-[r:{rel} {{{_EDGE_KEY_PROP}:${_EDGE_KEY_PROP}}}]->(b)\n"
        f"ON CREATE SET {_render_set('r', on_create)}\n"
        f"ON MATCH SET {_render_set('r', on_match)}"
    )


def all_node_templates() -> dict[str, MergeTemplate]:
    """Render a :class:`MergeTemplate` for every :class:`NodeLabel` (§3.8).

    Ключ словаря — строковое значение метки; поля берутся из :data:`NODE_FIELDS`
    (метка-специфично) либо из :data:`_DEFAULT_NODE_FIELDS`.
    """
    return {
        str(label): node_merge_cypher(str(label), NODE_FIELDS.get(label, _DEFAULT_NODE_FIELDS))
        for label in NodeLabel
    }


__all__ = [
    "NODE_FIELDS",
    "MergeTemplate",
    "node_merge_cypher",
    "edge_merge_cypher",
    "all_node_templates",
]
