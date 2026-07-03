"""§15.2 deterministic gap dedup_key + duplicate collapse (pure python).

RU: Детерминированный ключ дедупликации пробелов (gap) для §15.2. Ключ =
хеш от ``gap_type`` и **отсортированного множества** subject-id, поэтому повторные
сканы (re-scan) *обновляют* существующий пробел, а не плодят дубли. Порядок и
повторы subject-id не влияют на ключ. :func:`merge_gaps` схлопывает пробелы с общим
ключом, оставляя представителя с максимальным ``score`` и объединяя (union) его
``evidence_ids``.
EN: Deterministic gap dedup key for §15.2. The key is a hash of ``gap_type`` and the
**sorted, de-duplicated** subject-id set, so a re-scan updates an existing gap instead
of duplicating it. subject-id order/repeats do not change the key. :func:`merge_gaps`
collapses gaps that share a key, keeping the max-``score`` representative and unioning
its ``evidence_ids``.

Pure python — no store/graph/DB access: callers pass already-read gap ``dict``s.
Kuzu note: custom node props are NOT queryable columns — RETURN base columns and read
the rest via ``get_node()`` before assembling the gap dicts fed here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# §15.2: sha1 hex prefix length that keys the compact, stable dedup fingerprint.
_HASH_LEN = 12
DEFAULT_SCORE_KEY = "score"


def gap_dedup_key(gap_type: str, subject_ids: Iterable[str]) -> str:
    """Deterministic dedup key ``gap:<gap_type>:<sha1[:12]>`` for a gap (§15.2).

    Строит ключ из ``gap_type`` и **уникального отсортированного** множества
    ``subject_ids``: дубли отбрасываются, порядок нормализуется сортировкой, поэтому
    ключ инвариантен к порядку и повторам. Разный ``gap_type`` при том же множестве →
    разный ключ. Возвращает ``'gap:' + gap_type + ':' + sha1(...)[:12]``.

    The digest is over the sorted unique subject ids joined by ``\\x00`` (a separator
    that cannot occur inside an id), so distinct id sets cannot collide via joining.
    """
    unique_sorted = sorted(set(subject_ids))
    payload = "\x00".join(unique_sorted).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:_HASH_LEN]  # dedup fingerprint, not crypto
    return f"gap:{gap_type}:{digest}"


def _resolve_key(gap: dict[str, Any]) -> str:
    """Return a gap's precomputed ``dedup_key`` or compute it from its fields (§15.2)."""
    precomputed = gap.get("dedup_key")
    if precomputed:
        return str(precomputed)
    return gap_dedup_key(str(gap.get("gap_type", "")), gap.get("subject_ids", ()))


def _score_of(gap: dict[str, Any], score_key: str) -> float:
    """Extract a gap's score, defaulting to 0.0 if absent/non-numeric (§15.2)."""
    try:
        return float(gap.get(score_key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _union_evidence(base: Iterable[Any], extra: Iterable[Any]) -> list[Any]:
    """Order-preserving union of two ``evidence_ids`` sequences (§15.2)."""
    seen: dict[Any, None] = {}
    for item in base:
        seen.setdefault(item, None)
    for item in extra:
        seen.setdefault(item, None)
    return list(seen)


@dataclass(frozen=True)
class DedupResult:
    """Frozen result of :func:`merge_gaps` (§15.2).

    ``kept`` — представители после свёртки (по одному на уникальный ключ, порядок
    первого появления); ``collapsed`` — число схлопнутых дублей; ``keys`` — ключи
    представителей в том же порядке, что ``kept``.
    """

    kept: tuple[dict[str, Any], ...]
    collapsed: int
    keys: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§15.2, house style)."""
        return {
            "kept": [dict(gap) for gap in self.kept],
            "collapsed": self.collapsed,
            "keys": list(self.keys),
        }


def merge_gaps(gaps: list[dict], *, score_key: str = DEFAULT_SCORE_KEY) -> DedupResult:
    """Collapse gaps sharing a dedup key, keeping the max-score representative (§15.2).

    Идёт по ``gaps`` по порядку; ключ каждого берётся из готового ``dedup_key`` либо
    вычисляется из ``gap_type`` + ``subject_ids`` через :func:`gap_dedup_key`. Пробелы
    с одинаковым ключом схлопываются в одного представителя с максимальным ``score``
    (``score_key``); ``evidence_ids`` всех дублей объединяются (union, порядок появления)
    в выжившем. Представитель хранит свой ``dedup_key``. Позиция кластера — по первому
    появлению ключа; при равном ``score`` остаётся первый встреченный (ties → earlier).
    ``collapsed`` = число входов минус число уникальных ключей. Пустой вход → пустой
    результат. Возвращаются копии-``dict``; вход не мутируется.
    """
    rep: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    collapsed = 0
    for gap in gaps:
        key = _resolve_key(gap)
        if key not in rep:
            survivor = dict(gap)
            survivor["dedup_key"] = key
            rep[key] = survivor
            order.append(key)
            continue
        collapsed += 1
        current = rep[key]
        merged_evidence = _union_evidence(
            current.get("evidence_ids", ()),
            gap.get("evidence_ids", ()),
        )
        if _score_of(gap, score_key) > _score_of(current, score_key):  # strict → ties keep first
            survivor = dict(gap)
            survivor["dedup_key"] = key
            rep[key] = survivor
            current = survivor
        current["evidence_ids"] = merged_evidence
    kept = tuple(rep[key] for key in order)
    return DedupResult(kept=kept, collapsed=collapsed, keys=tuple(order))
