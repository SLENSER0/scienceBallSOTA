"""§11.11 — reconstruct EvidenceRefs (page + span) from a community report.

Восстановление ссылок на первоисточники (*EvidenceRefs* — ссылки на эвиденс) из
отчёта по кластеру знаний (*community report*). Для заданного кластера
прослеживается провенанс его сущностей-участников (*member entities*):

    (member {community_id})—[:Rel]—(Measurement)-[:SUPPORTED_BY]->(Evidence)

и по каждому эвиденсу собирается точная локация в документе-источнике
(документ): ``doc_id``, ``page`` и символьный диапазон ``char_start``/``char_end``
(span). Результат — дедуплицированный по ``evidence_id`` список
:class:`EvidenceRef`.

Kuzu note: пользовательские свойства узла (``char_start``/``char_end``) не являются
колонками и не читаются напрямую в ``RETURN`` — Cypher возвращает только базовые
``id``/``label``, а остальные поля читаются через :meth:`KuzuGraphStore.get_node`.

Deterministic and offline-safe (no LLM); complements the GraphRAG citations of
:mod:`kg_retrievers.graphrag_citations` (§11.11) with page + span precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("report_evidence")

# Provenance relation + labels traced from a community's members (§3.6 / §8.1).
_SUPPORTED_BY = "SUPPORTED_BY"
_MEASUREMENT_LABEL = "Measurement"
_EVIDENCE_LABEL = "Evidence"


@dataclass(frozen=True)
class EvidenceRef:
    """Точная ссылка на первоисточник за отчётом кластера (§11.11).

    Attributes:
        evidence_id: id узла Evidence (эвиденс).
        doc_id: id документа-источника (документ), либо ``None``.
        page: номер страницы в документе, либо ``None``.
        span_start: начало символьного диапазона (``char_start``), либо ``None``.
        span_end: конец символьного диапазона (``char_end``), либо ``None``.
    """

    evidence_id: str
    doc_id: str | None = None
    page: int | None = None
    span_start: int | None = None
    span_end: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict."""
        return {
            "evidence_id": self.evidence_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "span_start": self.span_start,
            "span_end": self.span_end,
        }


def _as_int(value: Any) -> int | None:
    """Coerce a stored offset/page (int / numeric str / None) to ``int`` or ``None``."""
    if value is None or isinstance(value, bool):  # bool is an int subclass — reject it
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _evidence_ids_for_community(store: KuzuGraphStore, community_id: int) -> list[str]:
    """Trace member→Measurement→Evidence, return distinct Evidence ids (§11.11).

    Matching uses only base ``id``/``label``/``type`` columns (Kuzu note); each
    Evidence's ``doc_id``/``page``/span are read later via ``get_node``.
    """
    rows = store.rows(
        "MATCH (m:Node)-[:Rel]-(meas:Node)-[s:Rel]->(ev:Node) "
        "WHERE m.community_id = $c AND meas.label = $meas "
        "AND s.type = $rt AND ev.label = $ev "
        "RETURN DISTINCT ev.id",
        {
            "c": community_id,
            "meas": _MEASUREMENT_LABEL,
            "rt": _SUPPORTED_BY,
            "ev": _EVIDENCE_LABEL,
        },
    )
    return [r[0] for r in rows if r[0]]


def report_to_evidence(store: KuzuGraphStore, community_id: int) -> list[EvidenceRef]:
    """Reconstruct EvidenceRefs (page + span) backing a community report (§11.11).

    Walks the community's member entities to their Measurements and the Evidence
    those measurements are ``SUPPORTED_BY``, reading each Evidence's ``doc_id``,
    ``page`` and character span (``char_start``/``char_end`` → ``span_start``/
    ``span_end``) via :meth:`KuzuGraphStore.get_node`. The result is deduplicated
    by ``evidence_id`` and sorted; an empty/unknown community yields ``[]``.
    """
    refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for ev_id in _evidence_ids_for_community(store, community_id):
        if ev_id in seen:  # dedup by evidence_id
            continue
        seen.add(ev_id)
        node = store.get_node(ev_id)
        if node is None:
            continue
        refs.append(
            EvidenceRef(
                evidence_id=ev_id,
                doc_id=node.get("doc_id"),
                page=_as_int(node.get("page")),
                span_start=_as_int(node.get("char_start")),
                span_end=_as_int(node.get("char_end")),
            )
        )
    refs.sort(key=lambda r: r.evidence_id)
    _log.info("report_evidence.reconstruct", community_id=community_id, refs=len(refs))
    return refs
