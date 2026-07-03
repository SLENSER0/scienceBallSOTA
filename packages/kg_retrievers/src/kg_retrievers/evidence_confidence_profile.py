"""§8.3 — evidence confidence & review-status profile for curation triage.

Агрегирует поля ``confidence`` и ``review_status`` всех узлов :Evidence в графе в
компактное распределение, полезное для сортировки очереди курации (*curation
triage*, §8.3): сколько всего эвиденсов, какова средняя/минимальная уверенность,
какие узлы «низкоуверенные» (ниже порога) и как раскладываются статусы ревью.

English: :func:`profile_evidence_confidence` scans every ``:Evidence`` node in a
:class:`~kg_retrievers.graph_store.KuzuGraphStore` and rolls its ``confidence`` and
``review_status`` into a frozen :class:`ConfidenceProfile`. Evidence with no numeric
confidence is *counted* in ``n_evidence`` but *excluded* from the mean, so a partly
unscored store still reports an honest average. A node is *low-confidence* when its
numeric ``confidence`` is strictly below ``low_threshold``.

Kuzu note: custom node props are not queryable columns, so we ``RETURN`` only the
base ``id`` column for ``:Evidence`` nodes, then re-hydrate each node through
:meth:`KuzuGraphStore.get_node` (which merges the ``props`` JSON) before reading
``confidence``/``review_status``. Pure, deterministic, offline-safe (no LLM).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kg_retrievers.graph_store import KuzuGraphStore

# Метка узла-эвиденса в дженерик-таблице Node (§3). Evidence node label.
EVIDENCE_LABEL: str = "Evidence"

# Порог низкой уверенности по умолчанию (§8.3). Default low-confidence threshold.
DEFAULT_LOW_THRESHOLD: float = 0.5


@dataclass(frozen=True)
class ConfidenceProfile:
    """Распределение уверенности/статусов ревью по эвиденсам (§8.3).

    Attributes:
        n_evidence: всего узлов :Evidence (включая без числовой уверенности).
        mean_confidence: средняя уверенность по узлам *с* числовым значением
            (``0.0`` если таких нет).
        min_confidence: минимальная числовая уверенность (``0.0`` если таких нет).
        low_confidence_ids: id узлов с ``confidence < low_threshold`` (в порядке обхода).
        review_status_counts: частоты значений ``review_status``.
    """

    n_evidence: int
    mean_confidence: float
    min_confidence: float
    low_confidence_ids: tuple[str, ...]
    review_status_counts: dict[str, int]

    @property
    def low_confidence_fraction(self) -> float:
        """Доля низкоуверенных эвиденсов от всех (``0.0`` при пустом графе)."""
        if self.n_evidence == 0:
            return 0.0
        return len(self.low_confidence_ids) / self.n_evidence

    def as_dict(self) -> dict[str, Any]:
        """Сериализация в plain-JSON-совместимый dict."""
        return {
            "n_evidence": self.n_evidence,
            "mean_confidence": self.mean_confidence,
            "min_confidence": self.min_confidence,
            "low_confidence_ids": list(self.low_confidence_ids),
            "review_status_counts": dict(self.review_status_counts),
            "low_confidence_fraction": self.low_confidence_fraction,
        }


def _numeric_confidence(node: dict[str, Any]) -> float | None:
    """Числовая уверенность узла в ``[..]`` или ``None`` (bool отбрасывается).

    ``bool`` — подкласс ``int``, но флаг никогда не является оценкой уверенности,
    поэтому ``True``/``False`` трактуются как «нет значения».
    """
    conf = node.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return None
    return float(conf)


def _review_status(node: dict[str, Any]) -> str | None:
    """Нормализованный (trim) ``review_status`` узла или ``None``, если пуст."""
    raw = node.get("review_status")
    if raw is None:
        return None
    status = str(raw).strip()
    return status or None


def profile_evidence_confidence(
    store: KuzuGraphStore, *, low_threshold: float = DEFAULT_LOW_THRESHOLD
) -> ConfidenceProfile:
    """Собрать §8.3-профиль уверенности/ревью по всем :Evidence узлам ``store``.

    Обход: берём ``id`` каждого ``:Evidence`` узла (единственная база-колонка,
    которую можно вернуть), затем читаем полный узел через
    :meth:`KuzuGraphStore.get_node`, чтобы получить смерженные из ``props``
    ``confidence`` и ``review_status``. Узел без числовой уверенности учитывается в
    ``n_evidence``, но не влияет на среднее; узел «низкоуверенный», если его числовая
    уверенность строго меньше ``low_threshold``.
    """
    rows = store.rows(
        "MATCH (n:Node {label:$label}) RETURN n.id ORDER BY n.id",
        {"label": EVIDENCE_LABEL},
    )

    n_evidence = 0
    confidences: list[float] = []
    low_ids: list[str] = []
    status_counts: dict[str, int] = {}

    for row in rows:
        node_id = row[0]
        node = store.get_node(node_id)
        if node is None:
            continue
        n_evidence += 1

        conf = _numeric_confidence(node)
        if conf is not None:
            confidences.append(conf)
            if conf < low_threshold:
                low_ids.append(node_id)

        status = _review_status(node)
        if status is not None:
            status_counts[status] = status_counts.get(status, 0) + 1

    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    min_confidence = min(confidences) if confidences else 0.0

    return ConfidenceProfile(
        n_evidence=n_evidence,
        mean_confidence=mean_confidence,
        min_confidence=min_confidence,
        low_confidence_ids=tuple(low_ids),
        review_status_counts=status_counts,
    )
