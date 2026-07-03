"""Active-learning sampler for the annotation protocol / QC (§23.26).

Annotation protocol and quality control: to spend annotator effort where the
model is least sure, this selects the highest-*uncertainty* unlabeled items for
the next annotation batch, with an optional per-type quota so no single item
type monopolizes the budget. Already-labeled items are dropped (and counted)
so re-runs never re-queue work that is already done.

Уверенность модели ``confidence`` in ``[0, 1]`` превращается в неопределённость
``uncertainty = 1 - |2*confidence - 1|`` — максимум ``1.0`` при ``0.5`` (модель
«не знает»), минимум ``0.0`` при ``0.0``/``1.0``. Отбор детерминирован: ранжируем
по убыванию неопределённости, ничьи разрываем по возрастанию ``id`` (§23.26:
протокол аннотирования и контроль качества — активный отбор с квотой по типам).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def uncertainty(confidence: float) -> float:
    """Uncertainty of a prediction — maximal (``1.0``) at ``confidence == 0.5``.

    Defined as ``1 - |2*confidence - 1|``: ``0.5`` maps to ``1.0`` (model is
    maximally unsure), while ``0.0`` and ``1.0`` both map to ``0.0`` (model is
    certain, in either direction).
    """
    return 1.0 - abs(2.0 * float(confidence) - 1.0)


@dataclass(frozen=True)
class SampleBatch:
    """One batch of items chosen for annotation.

    ``selected_ids`` are the chosen item ids in selection order (uncertainty
    desc, then id asc). ``skipped_labeled`` counts input items dropped because
    they were already labeled. ``per_type`` maps each represented type to how
    many of its items were selected; the counts sum to ``len(selected_ids)``.
    """

    selected_ids: tuple[str, ...]
    skipped_labeled: int
    per_type: Mapping[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "selected_ids": list(self.selected_ids),
            "skipped_labeled": self.skipped_labeled,
            "per_type": dict(self.per_type),
        }


def select(
    items: Sequence[Mapping[str, object]],
    *,
    k: int,
    max_per_type: int | None = None,
) -> SampleBatch:
    """Select up to ``k`` highest-uncertainty unlabeled ``items`` for annotation.

    Each item is a mapping with at least ``id`` and ``confidence``; an optional
    ``type`` (default ``"_"``) drives the per-type quota, and a truthy
    ``labeled`` flag drops the item from consideration (counted in
    ``skipped_labeled``). Remaining items are ranked by ``uncertainty`` desc,
    ties broken by ascending ``id``; when ``max_per_type`` is set, a type stops
    accepting items once it reaches that cap. The first ``k`` survivors form the
    batch.
    """
    if k < 0:
        raise ValueError("k must be non-negative")

    skipped_labeled = 0
    candidates: list[tuple[float, str, str]] = []
    for item in items:
        if item.get("labeled"):
            skipped_labeled += 1
            continue
        item_id = str(item["id"])
        item_type = str(item.get("type", "_"))
        candidates.append((uncertainty(float(item["confidence"])), item_id, item_type))

    # Uncertainty descending, then id ascending — fully deterministic order.
    candidates.sort(key=lambda c: (-c[0], c[1]))

    selected_ids: list[str] = []
    per_type: dict[str, int] = {}
    for _score, item_id, item_type in candidates:
        if len(selected_ids) >= k:
            break
        if max_per_type is not None and per_type.get(item_type, 0) >= max_per_type:
            continue
        selected_ids.append(item_id)
        per_type[item_type] = per_type.get(item_type, 0) + 1

    return SampleBatch(
        selected_ids=tuple(selected_ids),
        skipped_labeled=skipped_labeled,
        per_type=per_type,
    )
