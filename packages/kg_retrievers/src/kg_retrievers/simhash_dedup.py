"""Spec-exact §12.4 SimHash near-duplicate clustering (scalable dedup).

Отличный от :func:`kg_retrievers.<dedup>.dedup_hits` подход к устранению
near-дубликатов. Тот использует ``difflib.SequenceMatcher`` — попарное
сравнение символов с ``O(n²)`` char-ratio. Здесь — *fingerprint*-подход
Charikar SimHash: для каждого документа считается компактный ``bits``-битный
отпечаток по word-shingle'ам, а близость измеряется расстоянием Хэмминга.
Никакого пересечения по коду с char-ratio dedup — это масштабируемая
альтернатива.

Идея SimHash (§12.4):
  * текст → множество word-shingle'ов (по ``k`` соседних слов);
  * каждый shingle детерминированно хэшируется в ``bits``-битное число
    (``sha256`` — стабильно между запусками, в отличие от ``hash()``);
  * по каждому биту суммируем ``+1``/``-1`` для set/unset бита во всех
    shingle-хэшах; итоговый бит отпечатка = ``1`` при положительной сумме.
Похожие тексты делят большинство shingle'ов → близкие отпечатки → малый
Hamming. Порог ``max_hamming`` задаёт, что считать near-дубликатом.

Pure python — no store/graph access; caller passes ``docs`` уже собранными.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read text/score via ``get_node()`` before building ``docs``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class SimHashCluster:
    """Один кластер near-дубликатов: представитель + участники + отпечаток (§12.4)."""

    rep_id: str
    member_ids: tuple[str, ...]
    fingerprint: int

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug explainability (§12.4)."""
        return {
            "rep_id": self.rep_id,
            "member_ids": self.member_ids,
            "fingerprint": self.fingerprint,
        }


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens (Unicode ``\\w+``) — RU/EN friendly."""
    return _WORD_RE.findall(text.lower())


def _shingles(text: str, k: int = 2) -> list[str]:
    """Word-shingles по ``k`` соседних слов; fallback на одиночные слова.

    При числе слов ``< k`` возвращаем сами слова, чтобы короткие тексты тоже
    получали ненулевой набор shingle'ов.
    """
    tokens = _tokenize(text)
    if not tokens:
        return []
    if len(tokens) < k:
        return tokens
    return [" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]


def _hash_shingle(shingle: str, bits: int) -> int:
    """Детерминированный ``bits``-битный хэш shingle'а на базе ``sha256``."""
    digest = hashlib.sha256(shingle.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") & ((1 << bits) - 1)


def simhash(text: str, bits: int = 64) -> int:
    """Charikar SimHash отпечаток текста (§12.4), детерминированный.

    Возвращает целое в диапазоне ``0 <= fp < 2**bits``. Пустой текст (без
    словных токенов) даёт ``0``. Одинаковый вход всегда даёт одинаковый выход
    (используется ``sha256``, не salted ``hash()``).
    """
    shingles = _shingles(text)
    if not shingles:
        return 0
    counts = [0] * bits
    for shingle in shingles:
        h = _hash_shingle(shingle, bits)
        for i in range(bits):
            if (h >> i) & 1:
                counts[i] += 1
            else:
                counts[i] -= 1
    fingerprint = 0
    for i in range(bits):
        if counts[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming(a: int, b: int) -> int:
    """Hamming distance = popcount of ``a XOR b`` (§12.4).

    Рефлексивно (``hamming(x, x) == 0``) и симметрично
    (``hamming(a, b) == hamming(b, a)``).
    """
    return (a ^ b).bit_count()


def cluster_near_dupes(
    docs: dict[str, str],
    max_hamming: int = 3,
    scores: dict[str, float] | None = None,
) -> list[SimHashCluster]:
    """Кластеризует ``docs`` по близости SimHash-отпечатков (§12.4).

    Два документа связаны, если их отпечатки в пределах ``max_hamming`` по
    Хэммингу; связность транзитивно замыкается (union-find). Представитель
    кластера — участник с максимальным ``scores[id]`` (ничьи — по порядку
    вставки); при ``scores is None`` — первый по порядку вставки участник.
    ``fingerprint`` кластера — отпечаток представителя. Кластеры и их
    ``member_ids`` упорядочены по исходному порядку ``docs``.
    """
    ids = list(docs)
    fps = {doc_id: simhash(docs[doc_id]) for doc_id in ids}

    parent = {doc_id: doc_id for doc_id in ids}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if hamming(fps[ids[i]], fps[ids[j]]) <= max_hamming:
                union(ids[i], ids[j])

    groups: dict[str, list[str]] = {}
    for doc_id in ids:  # insertion order preserved
        groups.setdefault(find(doc_id), []).append(doc_id)

    clusters: list[SimHashCluster] = []
    for members in groups.values():
        if scores is not None:
            rep = max(members, key=lambda m: scores.get(m, float("-inf")))
        else:
            rep = members[0]
        clusters.append(
            SimHashCluster(
                rep_id=rep,
                member_ids=tuple(members),
                fingerprint=fps[rep],
            )
        )
    return clusters
