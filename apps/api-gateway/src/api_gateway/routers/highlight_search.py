"""Поиск с highlight-фрагментами (`<em>`-подсветка совпадений) — §4.7.

Endpoint ``GET /api/v1/search/highlight`` ищет узлы графа (name / aliases /
canonical_name / text) по запросу и для каждого хита возвращает
``<em>``-фрагменты того поля, где нашлось совпадение — точный спан, по которому
найден результат (evidence/доверие). Highlight-семантика (``pre_tags`` /
``post_tags`` / ``fragment_size`` / ``number_of_fragments``) реализована чистым
модулем :mod:`api_gateway.search_highlight`; здесь только маршрутизация к живому
Neo4j-store (server-профиль, :8000).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store
from api_gateway.search_highlight import (
    DEFAULT_POST,
    DEFAULT_PRE,
    Fragment,
    build_fragments,
    match_score,
    tokenize,
)

router = APIRouter(prefix="/api/v1", tags=["search"])

# Поля узла, по которым ищем и строим подсветку — от самого «текстового» к меткам.
_FIELDS = ("text", "name", "aliases_text", "canonical_name")

_SEARCH_CYPHER = (
    "MATCH (n:Node) WHERE ("
    "lower(coalesce(n.text,'')) CONTAINS $t "
    "OR lower(coalesce(n.name,'')) CONTAINS $t "
    "OR lower(coalesce(n.aliases_text,'')) CONTAINS $t "
    "OR lower(coalesce(n.canonical_name,'')) CONTAINS $t) "
    "RETURN n LIMIT $lim"
)


def _best_field(node: dict[str, Any], terms: list[str]) -> tuple[str, str] | None:
    """Выбрать поле узла с наибольшим числом совпадений (текст приоритетнее меток)."""
    best: tuple[float, int, str, str] | None = None
    for rank, key in enumerate(_FIELDS):
        val = node.get(key)
        if not isinstance(val, str) or not val.strip():
            continue
        sc = match_score(val, terms)
        # Ключ сортировки: больше совпадений → раньше в _FIELDS → длиннее текст.
        cand = (sc, -rank, key, val)
        if sc > 0 and (best is None or cand > best):
            best = cand
    if best is None:
        return None
    return best[2], best[3]


@router.get("/search/highlight")
def search_highlight(
    q: str = Query(min_length=1, description="Поисковый запрос"),
    limit: int = Query(default=15, ge=1, le=100),
    fragment_size: int = Query(default=160, ge=40, le=600),
    fragments: int = Query(default=3, ge=1, le=8),
    pre_tag: str = Query(default=DEFAULT_PRE),
    post_tag: str = Query(default=DEFAULT_POST),
) -> dict:
    """Хиты + ``<em>``-фрагменты вокруг совпадений запроса (§4.7).

    Возвращает ``{query, count, pre_tag, post_tag, results:[{id, name, type,
    doc_id, page, score, field, fragments:[{html, matched_terms}]}]}``.
    Ранжирование — по доле совпавших термов запроса.
    """
    store = get_store()
    terms = tokenize(q)
    # Берём с запасом (совпадение по подстроке ≠ пословное), затем ранжируем/режем.
    rows = store.rows(_SEARCH_CYPHER, {"t": q.lower(), "lim": int(limit) * 6})

    hits: list[dict[str, Any]] = []
    for r in rows:
        node = store._node_dict(r[0])
        picked = _best_field(node, terms)
        if picked is None:
            continue
        field_name, text = picked
        frags: list[Fragment] = build_fragments(
            text,
            terms,
            pre_tag=pre_tag,
            post_tag=post_tag,
            fragment_size=fragment_size,
            number_of_fragments=fragments,
        )
        if not frags:
            continue
        hits.append(
            {
                "id": node["id"],
                "name": node.get("name"),
                "type": node.get("label"),
                "doc_id": node.get("doc_id"),
                "page": node.get("page"),
                "domain": node.get("domain"),
                "review_status": node.get("review_status"),
                "score": round(match_score(text, terms), 4),
                "field": field_name,
                "fragments": [f.as_dict() for f in frags],
            }
        )

    hits.sort(key=lambda h: h["score"], reverse=True)
    hits = hits[: int(limit)]
    return {
        "query": q,
        "count": len(hits),
        "pre_tag": pre_tag,
        "post_tag": post_tag,
        "results": hits,
    }
