"""Vector index specification for node embeddings (§3.13).

Модуль :mod:`kg_schema.index_selection` описывает property/range-индексы, но не
покрывает **векторный индекс** (*vector index*) для эмбеддингов узлов. §3.13
фиксирует ``entity_embedding_index`` над ``Entity.embedding`` (размерность
``1024``, метрика ``cosine``) и требует проверки согласованности размерности
(*dimension-consistency check*). Этот модуль добавляет декларативную
спецификацию индекса, её сериализацию в Cypher и чистые (*pure*) валидаторы
эмбеддингов и косинусной близости.

Kuzu note: на встроенном профиле кастомные свойства узла (в т.ч. ``embedding``)
НЕ являются запрашиваемыми колонками — их читают через ``get_node()``. Векторный
индекс — намерение серверного профиля (Neo4j); спецификация остаётся
декларативной и к хранилищу не обращается.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VectorIndexSpec:
    """Declarative vector-index spec for a node label's embedding property (§3.13).

    Attributes
    ----------
    name:
        Имя индекса (*index name*), например ``"entity_embedding_index"``.
    label:
        Целевая метка узла (*node label*), например ``"Entity"``.
    property:
        Имя свойства-эмбеддинга (*embedding property*), например ``"embedding"``.
    dimensions:
        Размерность вектора (*vector dimensionality*), например ``1024``.
    similarity:
        Метрика близости (*similarity function*), например ``"cosine"``.
    """

    name: str
    label: str
    property: str
    dimensions: int
    similarity: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict for API / schema-view callers (§3.13)."""
        return {
            "name": self.name,
            "label": self.label,
            "property": self.property,
            "dimensions": self.dimensions,
            "similarity": self.similarity,
        }

    def to_cypher(self) -> str:
        """Render the ``CREATE VECTOR INDEX`` DDL for the server profile (§3.13).

        Формат соответствует Neo4j: имя индекса, метка/свойство узла и опции
        ``vector.dimensions`` / ``vector.similarity_function``.
        """
        return (
            f"CREATE VECTOR INDEX {self.name} IF NOT EXISTS\n"
            f"FOR (n:{self.label}) ON (n.{self.property})\n"
            "OPTIONS { indexConfig: {\n"
            f"  `vector.dimensions`: {self.dimensions},\n"
            f"  `vector.similarity_function`: '{self.similarity}'\n"
            "} }"
        )


# §3.13: закреплённый (*pinned*) векторный индекс для эмбеддингов сущностей.
ENTITY_EMBEDDING_INDEX: VectorIndexSpec = VectorIndexSpec(
    "entity_embedding_index",
    "Entity",
    "embedding",
    1024,
    "cosine",
)


def validate_embedding(
    vec: Sequence[float],
    spec: VectorIndexSpec = ENTITY_EMBEDDING_INDEX,
) -> tuple[bool, list[str]]:
    """Check ``vec`` matches ``spec`` dimensionality and is all-finite (§3.13).

    Возвращает ``(ok, errors)``: ``ok`` истинно, если длина равна
    ``spec.dimensions`` И все компоненты конечны (*finite*, не ``NaN``/``inf``).
    """
    errors: list[str] = []
    if len(vec) != spec.dimensions:
        errors.append(f"expected dimensions {spec.dimensions}, got {len(vec)}")
    for i, x in enumerate(vec):
        if not math.isfinite(x):
            errors.append(f"non-finite component at index {i}: {x!r}")
    return (not errors, errors)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between vectors ``a`` and ``b`` (§3.13).

    Возвращает ``0.0`` для нулевого вектора (*zero vector*), чтобы избежать
    деления на ноль; иначе ``dot(a, b) / (||a|| * ||b||)``.
    """
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def self_nearest(query: Sequence[float], candidates: Mapping[str, Sequence[float]]) -> str:
    """Return the id of the argmax-cosine candidate for ``query`` (§3.13).

    Имитирует запрос к векторному индексу поверх словаря кандидатов
    (*candidate map*); возвращает идентификатор ближайшего по косинусу вектора.
    """
    if not candidates:
        raise ValueError("candidates must be non-empty")
    return max(candidates, key=lambda k: cosine(query, candidates[k]))
