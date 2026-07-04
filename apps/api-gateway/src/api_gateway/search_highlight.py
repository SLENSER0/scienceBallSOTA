"""Highlight-фрагменты (`<em>`-подсветка) для результатов поиска (§4.7).

Критерий приёмки §4.7 требует highlight-секцию OpenSearch-семантики (`pre_tags` /
`post_tags`, `fragment_size`, `number_of_fragments`), которая возвращает
``<em>``-фрагменты вокруг спана, по которому найден хит. В live server-профиле
поиск идёт по Neo4j (не по OpenSearch), поэтому этот модуль — чистая, тестируемая
реализация тех же семантик поверх произвольного текста узла:

* :class:`Fragment`      — один фрагмент: готовый HTML (с ``<em>``) + сопоставленные термы.
* :func:`tokenize`       — разбить запрос на термы (RU+EN, слова/числа).
* :func:`build_fragments`— построить top-N ``<em>``-фрагментов вокруг совпадений.

Безопасность: весь исходный текст HTML-экранируется (``html.escape``), а теги
``pre_tag`` / ``post_tag`` вставляются поверх — в выдаче не может оказаться чужой
разметки, только наши ``<em>``-теги. Совпадения ищутся по началу слова
(term — префикс слова или слово — префикс term), что даёт стемминг-подобную
подсветку («hard» подсвечивает «hardness»).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

# Токен — последовательность букв/цифр (unicode: покрывает кириллицу и латиницу),
# подчёркивание исключено, чтобы не склеивать идентификаторы.
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

DEFAULT_PRE = "<em>"
DEFAULT_POST = "</em>"


@dataclass(frozen=True, slots=True)
class Fragment:
    """Один highlight-фрагмент (§4.7): готовый HTML + список сопоставленных термов."""

    html: str
    matched_terms: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, object]:
        return {"html": self.html, "matched_terms": list(self.matched_terms)}


def tokenize(query: str) -> list[str]:
    """Разбить запрос на уникальные термы (нижний регистр, ≥2 символов либо число)."""
    seen: dict[str, None] = {}
    for m in _WORD.finditer(query or ""):
        w = m.group(0).lower()
        if len(w) >= 2 or w.isdigit():
            seen.setdefault(w, None)
    return list(seen)


def _word_matches(word_lower: str, terms: list[str]) -> str | None:
    """Вернуть сопоставленный терм, если слово совпадает с одним из термов.

    Совпадение — слово начинается с терма (``aging`` ↔ терм ``aging``) или терм
    начинается со слова при длине слова ≥3 (лёгкий стемминг). Возвращает первый
    подходящий терм или ``None``.
    """
    for t in terms:
        if word_lower.startswith(t) or (len(word_lower) >= 3 and t.startswith(word_lower)):
            return t
    return None


def _match_spans(text: str, terms: list[str]) -> list[tuple[int, int, str]]:
    """Найти спаны ``[start, end)`` слов текста, совпавших с термами запроса."""
    low = text.lower()
    spans: list[tuple[int, int, str]] = []
    for m in _WORD.finditer(text):
        t = _word_matches(low[m.start() : m.end()], terms)
        if t is not None:
            spans.append((m.start(), m.end(), t))
    return spans


def _snap_left(text: str, i: int) -> int:
    """Сдвинуть левую границу к началу текущего слова, чтобы не резать слово."""
    while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
        i -= 1
    return i


def _snap_right(text: str, i: int) -> int:
    """Сдвинуть правую границу к концу текущего слова."""
    n = len(text)
    while i < n and (text[i].isalnum() or text[i] == "_"):
        i += 1
    return i


def _render(
    text: str,
    ws: int,
    we: int,
    spans: list[tuple[int, int, str]],
    pre: str,
    post: str,
) -> tuple[str, tuple[str, ...]]:
    """Собрать HTML фрагмента ``[ws, we)``: экранировать текст, обернуть совпадения."""
    parts: list[str] = []
    matched: dict[str, None] = {}
    cur = ws
    for s, e, term in spans:
        if e <= ws or s >= we:
            continue
        s2, e2 = max(s, ws), min(e, we)
        if s2 > cur:
            parts.append(html.escape(text[cur:s2]))
        parts.append(pre + html.escape(text[s2:e2]) + post)
        matched.setdefault(term, None)
        cur = e2
    if cur < we:
        parts.append(html.escape(text[cur:we]))
    body = "".join(parts)
    if ws > 0:
        body = "…" + body
    if we < len(text):
        body = body + "…"
    return body, tuple(matched)


def build_fragments(
    text: str,
    terms: list[str],
    *,
    pre_tag: str = DEFAULT_PRE,
    post_tag: str = DEFAULT_POST,
    fragment_size: int = 160,
    number_of_fragments: int = 3,
) -> list[Fragment]:
    """Построить top-N ``<em>``-фрагментов вокруг совпадений термов в тексте (§4.7).

    Семантика повторяет highlight-секцию OpenSearch: окно ширины ``fragment_size``
    вокруг каждого совпадения, перекрывающиеся окна сливаются, из них берутся
    ``number_of_fragments`` наиболее насыщенных совпадениями (по убыванию),
    затем сортируются по позиции для показа. Если совпадений нет — возвращается
    один головной сниппет без подсветки.
    """
    text = text or ""
    if not text.strip():
        return []
    spans = _match_spans(text, terms) if terms else []
    if not spans:
        head = text[:fragment_size].rstrip()
        body = html.escape(head) + ("…" if len(text) > len(head) else "")
        return [Fragment(html=body, matched_terms=())]

    half = max(fragment_size // 2, 20)
    # Одно окно на совпадение, привязанное к границам слов.
    raw: list[list[int]] = []
    for s, e, _t in spans:
        c = (s + e) // 2
        ws = _snap_left(text, max(0, c - half))
        we = _snap_right(text, min(len(text), c + half))
        raw.append([ws, we])
    raw.sort()

    merged: list[list[int]] = []
    for w in raw:
        if merged and w[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], w[1])
        else:
            merged.append(list(w))

    scored: list[tuple[int, int, int]] = []  # (n_spans, ws, we)
    for ws, we in merged:
        n = sum(1 for s, e, _t in spans if s < we and e > ws)
        scored.append((n, ws, we))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = sorted(scored[: max(1, number_of_fragments)], key=lambda x: x[1])

    out: list[Fragment] = []
    for _n, ws, we in top:
        body, matched = _render(text, ws, we, spans, pre_tag, post_tag)
        out.append(Fragment(html=body, matched_terms=matched))
    return out


def match_score(text: str, terms: list[str]) -> float:
    """Доля термов запроса, встретившихся в тексте — для ранжирования хитов (§4.7)."""
    if not terms:
        return 0.0
    hit = {t for _s, _e, t in _match_spans(text or "", terms)}
    return len(hit) / len(terms)
