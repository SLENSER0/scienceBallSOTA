"""§24.7 — knowledge_verification_report over the Kuzu graph store.

Отчёт о верификации знаний (*knowledge verification report*). Для каждого домена
(предметной области) считается доля фактов (*facts* — узлы ``Measurement`` и
``TechnologySolution``), чей статус верификации (*verification_status*) равен
``verified`` / ``reviewed`` / ``pending`` / ``obsolete``. Отсутствующий статус
трактуется как ``pending`` (не проверено). Доли внутри домена суммируются в 1.0
(при непустом домене), что даёт быстрый обзор «зрелости» знаний по областям.

Дополнительно :func:`is_source_obsolete` помечает устаревшие источники —
патенты и стандарты (*patents / standards*, узлы с меткой ``Patent`` / ``Standard``),
у которых ``effective_date`` либо ``year`` старше порога ``max_age_years``.

Kuzu note: пользовательское свойство ``verification_status`` не является колонкой
таблицы ``Node`` и не читается напрямую в ``RETURN`` — Cypher возвращает только
базовые ``id`` / ``domain``, а статус читается пофактно через
:meth:`KuzuGraphStore.get_node`.

«Сейчас» (``now_iso``) всегда передаётся явно — модуль детерминирован и не
обращается к системным часам (no ``datetime.now``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema import VerificationLevel

# Verification-status buckets (§24.7). ``obsolete`` reuses the schema enum value.
STATUS_VERIFIED = "verified"
STATUS_REVIEWED = "reviewed"
STATUS_PENDING = "pending"
STATUS_OBSOLETE = VerificationLevel.OBSOLETE.value  # "obsolete"

# Ordered tuple used for every counts/shares dict (stable key order).
STATUSES: tuple[str, ...] = (STATUS_VERIFIED, STATUS_REVIEWED, STATUS_PENDING, STATUS_OBSOLETE)
_STATUS_SET = frozenset(STATUSES)

# Node labels treated as verifiable "facts" (§24.7).
FACT_LABELS: tuple[str, ...] = ("Measurement", "TechnologySolution")

# Source labels whose age is checked for staleness (patents / standards).
SOURCE_LABELS: frozenset[str] = frozenset({"Standard", "Patent"})

# Domain bucket for facts that carry no ``domain`` value.
UNKNOWN_DOMAIN = "unknown"


@dataclass(frozen=True)
class VerificationReport:
    """Per-domain verification shares plus an aggregate total (§24.7).

    Attributes:
        by_domain: домен → ``{"total", "counts", "shares"}``; ``counts`` и
            ``shares`` содержат по одному значению на каждый статус из
            :data:`STATUSES`. ``shares`` суммируются в 1.0 при ``total > 0``.
        totals: та же структура, агрегированная по всем учтённым фактам.
    """

    by_domain: dict[str, dict[str, Any]]
    totals: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict."""
        return {"by_domain": self.by_domain, "totals": self.totals}


def _bucket(status: Any) -> str:
    """Normalise a raw ``verification_status`` to a known bucket (missing → pending)."""
    if isinstance(status, str) and status in _STATUS_SET:
        return status
    return STATUS_PENDING


def _stats(counts: dict[str, int]) -> dict[str, Any]:
    """Build ``{"total", "counts", "shares"}`` from per-status counts.

    Shares are ``count / total`` (0.0 for every status when ``total == 0``, so the
    result is well-defined for empty domains).
    """
    total = sum(counts[s] for s in STATUSES)
    shares = {s: (counts[s] / total if total else 0.0) for s in STATUSES}
    return {
        "total": total,
        "counts": {s: counts[s] for s in STATUSES},
        "shares": shares,
    }


def _zero_counts() -> dict[str, int]:
    return dict.fromkeys(STATUSES, 0)


def knowledge_verification_report(
    store: KuzuGraphStore, *, domain: str | None = None
) -> VerificationReport:
    """Compute per-domain verification shares over fact nodes (§24.7).

    Facts are ``Measurement`` / ``TechnologySolution`` nodes. Their ``domain`` is
    read from the base column; the ``verification_status`` (a non-column custom
    property, per the Kuzu note) is read via :meth:`KuzuGraphStore.get_node` and
    bucketed by :func:`_bucket` (missing → ``pending``).

    When ``domain`` is given only that domain's facts are counted, and the domain
    is always present in ``by_domain`` — an all-zero (shares 0.0) entry if it holds
    no facts. Without a filter, facts lacking a ``domain`` are grouped under
    :data:`UNKNOWN_DOMAIN`. ``totals`` aggregates exactly the counted facts.
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels RETURN n.id, n.domain",
        {"labels": list(FACT_LABELS)},
    )
    per_domain: dict[str, dict[str, int]] = {}
    total_counts = _zero_counts()
    for node_id, node_domain in rows:
        dom = node_domain or UNKNOWN_DOMAIN
        if domain is not None and dom != domain:
            continue
        node = store.get_node(node_id)
        status = _bucket(node.get("verification_status") if node else None)
        per_domain.setdefault(dom, _zero_counts())[status] += 1
        total_counts[status] += 1

    if domain is not None:  # requested domain always present, even if empty
        per_domain.setdefault(domain, _zero_counts())

    by_domain = {dom: _stats(per_domain[dom]) for dom in sorted(per_domain)}
    return VerificationReport(by_domain=by_domain, totals=_stats(total_counts))


def _year_of(value: Any) -> int | None:
    """Extract a 4-digit year from an int, ISO date/datetime, or bare year string."""
    if value is None or isinstance(value, bool):  # bool is an int subclass — reject it
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():  # "2010", "2010-01-01", "2010-01-01T.."
        return int(text[:4])
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def is_source_obsolete(node: dict[str, Any], *, now_iso: str, max_age_years: float) -> bool:
    """Flag a stale patent / standard whose date is older than ``max_age_years`` (§24.7).

    Applies only to nodes labelled ``Standard`` / ``Patent``; any other label returns
    ``False``. The source year is taken from ``effective_date`` (ISO, year-precise)
    or, failing that, the ``year`` column. ``now_iso`` supplies the reference year
    (passed explicitly — never ``datetime.now``). Returns ``False`` when the label
    is not a source or no date can be determined.
    """
    if node.get("label") not in SOURCE_LABELS:
        return False
    now_year = _year_of(now_iso)
    src_year = _year_of(node.get("effective_date"))
    if src_year is None:
        src_year = _year_of(node.get("year"))
    if now_year is None or src_year is None:
        return False
    return (now_year - src_year) > max_age_years
