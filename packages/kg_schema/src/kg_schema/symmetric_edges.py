"""§3.5 — symmetric relationship canonicalization / канонизация симметричных рёбер.

``relationships.py`` объявляет :data:`kg_schema.relationships.SYMMETRIC_RELS`
(``{CONTRADICTS, COMPARES_WITH}``), но ничего это множество не потребляет. §3.5
требует хранить симметричное ребро (*symmetric edge*) один раз и читать его в обе
стороны: ``A —CONTRADICTS→ B`` и ``B —CONTRADICTS→ A`` — это одно и то же ребро.

Этот модуль даёт канонизацию (*canonicalization*): для симметричного типа связи
концы (*endpoints*) упорядочиваются лексикографически, поэтому пары ``A/B`` и
``B/A`` схлопываются (*collapse*) в один канонический ключ. Асимметричные связи
(*asymmetric rels*) сохраняют заданный порядок ``source → target``.

Модуль НИЧЕГО не переопределяет: множество симметричных типов читается из
:data:`kg_schema.relationships.SYMMETRIC_RELS`.

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают
через ``get_node()``. Здесь речь о форме ребра (source/target/rel_type), а не о
хранении графа, поэтому ограничение не затрагивается.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from kg_schema.relationships import SYMMETRIC_RELS


@dataclass(frozen=True, slots=True)
class CanonicalEdge:
    """Canonical (source, target, rel_type) triple / канонический тройной ключ ребра."""

    source: str
    target: str
    rel_type: str

    def as_dict(self) -> dict[str, str]:
        """Serializable dict / сериализуемый словарь ребра."""
        return asdict(self)

    def key(self) -> tuple[str, str, str]:
        """Hashable dedupe key / хешируемый ключ дедупликации."""
        return (self.source, self.target, self.rel_type)


def is_symmetric(rel_type: str) -> bool:
    """True iff ``rel_type`` is symmetric / симметричен ли тип связи (§3.5)."""
    return rel_type in SYMMETRIC_RELS


def canonical_edge(source: str, target: str, rel_type: str) -> CanonicalEdge:
    """Canonicalize an edge / канонизировать ребро.

    Для симметричных связей концы упорядочиваются лексикографически (``A/B`` и
    ``B/A`` схлопываются); для асимметричных сохраняется заданный порядок.
    """
    if is_symmetric(rel_type) and source > target:
        source, target = target, source
    return CanonicalEdge(source=source, target=target, rel_type=rel_type)


def dedupe_symmetric(edges: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Collapse duplicate symmetric pairs / схлопнуть дубли симметричных пар (§3.5).

    Симметричные рёбра дедуплицируются по каноническому ключу (``A/B`` == ``B/A``);
    асимметричные рёбра сохраняются как есть (с учётом дублей по их ключу).
    Порядок первого появления сохраняется.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for edge in edges:
        canon = canonical_edge(edge["source"], edge["target"], edge["rel_type"])
        if canon.key() in seen:
            continue
        seen.add(canon.key())
        out.append(canon.as_dict())
    return out
