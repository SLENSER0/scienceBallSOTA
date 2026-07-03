"""§11.6 community-boost re-ranking for hybrid retrieval.

Ре-ранжирование гибридной выдачи по признаку «чанк из того же сообщества»
(§11.6). Спека дублирует ``community_id`` в payload чанка именно для того, чтобы
гибридный ретривер мог применить общий community-boost поверх базового скоринга —
здесь эта логика вынесена в один pure-python проход.

Rationale: :func:`kg_retrievers.proximity.proximity_level` оценивает лишь *пару*
узлов, а scoring/hybrid/fusion не содержат community-логики (``community_boost=0``
там всюду). Этот модуль поднимает pointwise-скоринг до уровня всего ранжированного
списка: каждому чанку, чей ``community_id`` входит в множество «горячих» сообществ
``boost_communities``, к базовому скору добавляется ровно ``boost`` (по умолчанию
``0.2``, как в §11.6); остальные сохраняют базовый скор. ``community_id=None``
никогда не буститься. Итог сортируется по ``boosted_score`` убыв., тай-брейк —
``chunk_id`` по возр., поэтому забустенный чанк с меньшим базовым скором может
обогнать незабустенный с большим.

Pure python — no store/graph/DB access: на вход уже собранные payload-``Mapping``.
Kuzu note: custom node props are NOT queryable columns — ``community_id`` кладётся
в payload заранее (RETURN base columns, остальное через ``get_node``), а здесь
читается прямо из переданных ``dict``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# §11.6 дефолтная величина community-boost. Default same-community boost.
DEFAULT_BOOST: float = 0.2


@dataclass(frozen=True)
class BoostedChunk:
    """Один чанк после community-boost (§11.6). One chunk after the community boost.

    ``chunk_id`` — идентификатор; ``base_score`` — исходный скор гибридной выдачи;
    ``community_id`` — сообщество чанка (``None``, если неизвестно и никогда не
    буститься); ``boosted_score`` — итоговый скор = ``base_score`` (+``boost``, если
    ``community_id`` входит в горячее множество).
    """

    chunk_id: str
    base_score: float
    community_id: str | None
    boosted_score: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection; ``boosted_score`` отражает применённый boost (§11.6)."""
        return {
            "chunk_id": self.chunk_id,
            "base_score": self.base_score,
            "community_id": self.community_id,
            "boosted_score": self.boosted_score,
        }


def apply_community_boost(
    chunks: Sequence[Mapping[str, Any]],
    boost_communities: set[str],
    boost: float = DEFAULT_BOOST,
) -> list[BoostedChunk]:
    """Apply the §11.6 same-community boost across a ranked chunk list.

    Каждый ``Mapping`` даёт ``chunk_id``, ``score`` и ``community_id``. К базовому
    скору прибавляется ``boost`` тогда и только тогда, когда ``community_id`` не
    ``None`` и входит в ``boost_communities``; иначе итог равен базовому. Результат
    сортируется по ``boosted_score`` убыв., равные — по ``chunk_id`` возр. Пустой
    вход → ``[]``.
    """
    result: list[BoostedChunk] = []
    for ch in chunks:
        chunk_id = str(ch["chunk_id"])
        base = float(ch["score"])
        community_id = ch.get("community_id")
        # community_id=None никогда не буститься (§11.6). None is never boosted.
        hot = community_id is not None and community_id in boost_communities
        boosted = base + boost if hot else base
        result.append(
            BoostedChunk(
                chunk_id=chunk_id,
                base_score=base,
                community_id=community_id,
                boosted_score=boosted,
            )
        )
    # Убыв. по boosted_score, тай-брейк — chunk_id возр. Desc score, asc id tie-break.
    result.sort(key=lambda c: (-c.boosted_score, c.chunk_id))
    return result
