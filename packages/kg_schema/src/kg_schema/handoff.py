"""Pipeline stage handoff contracts (§6.16 / §23.2).

Каждый стык конвейера (*pipeline stage boundary*) описан формальной Pydantic-схемой,
чтобы дрейф контракта (*contract drift*) ловился contract-тестом на CI (§23.2). Схемы
покрывают четыре стыка Step 4→7 (§9.2):

* **chunk** — ingestion→extraction: чанк документа на вход экстрактору (§5.9).
* **extraction** — extraction→normalization: сырые факты + флаг
  ``needs_custom_normalization`` (HV/HRC, которые ``pint`` не приводит — §6.3/§6.16).
* **normalization** — normalization→upsert: нормализованные измерения + отбракованные
  (*flagged*), требующие ручной нормализации (§9.2 Step 5).
* **er** — extraction→entity-resolution: сырые упоминания (*mentions*) на Splink (§8).
* **upsert** — er→upsert / upsert→indexing: граф-готовый узел с провенансом (§8.9/§4.10).

Все модели наследуют :class:`kg_common.dto.CamelModel`, поэтому JSON-полезная нагрузка
идёт в camelCase (``needsCustomNormalization``), а Python-код — в snake_case
(``populate_by_name=True``). Лишние поля отбрасываются (``extra="ignore"``), унаследовано
от ``CamelModel`` — dto.py здесь НЕ редактируется.

``validate_handoff`` диспетчеризует по имени стыка через :data:`HANDOFF_MODELS` и отдаёт
``{"valid": bool, "errors": list[str]}`` — пригодно и для CI-gate, и для рантайм-проверки.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, ValidationError

from kg_common.dto import CamelModel


class ChunkHandoff(CamelModel):
    """ingestion→extraction: один чанк документа на вход экстрактору (§5.9).

    ``chunk_id`` / ``doc_id`` / ``text`` обязательны — без них экстрактор не может ни
    привязать факт к источнику, ни сформировать детерминированный ``evidence_id`` (§8.4).
    """

    chunk_id: str
    doc_id: str
    text: str
    section_path: str | None = None
    chunk_type: str = "text"
    tokens: int | None = None


class ExtractionHandoff(CamelModel):
    """extraction→normalization: сырые факты чанка + флаг нормализации (§6.16).

    ``needs_custom_normalization`` поднимается, когда среди ``measurements`` есть единицы,
    которые ``pint`` не приводит (HV/HRC — твёрдость, §6.3); их доводит Step 5, здесь поля
    ``value_normalized``/``normalized_unit`` НЕ заполняются.
    """

    chunk_id: str
    entities: list[dict[str, Any]] = Field(default_factory=list)
    measurements: list[dict[str, Any]] = Field(default_factory=list)
    needs_custom_normalization: bool = False


class NormalizationHandoff(CamelModel):
    """normalization→upsert: нормализованные измерения + отбракованные (§9.2 Step 5).

    ``flagged`` — измерения, которые нормализатор не смог привести (например, кастомные
    шкалы твёрдости) и которые уходят на ручную доводку/куратора, а не в граф.
    """

    measurements: list[dict[str, Any]] = Field(default_factory=list)
    flagged: list[dict[str, Any]] = Field(default_factory=list)


class ERHandoff(CamelModel):
    """extraction→entity-resolution: сырые упоминания на Splink (§8).

    ``mentions`` — сырые ``material_mentions``/``equipment_mentions``/``lab_mentions`` и т.п.
    одного типа сущности ``entity_type`` (§9.2 Step 6). Резолюция здесь НЕ выполняется.
    """

    mentions: list[dict[str, Any]] = Field(default_factory=list)
    entity_type: str


class UpsertHandoff(CamelModel):
    """er→upsert / upsert→indexing: граф-готовый узел с провенансом (§8.9 / §4.10).

    ``props`` — свойства узла (catch-all), ``provenance`` — обязательный след происхождения
    (``extractor_run_id``/``schema_version``/``created_at``, §3.7). Сам upsert здесь НЕ
    выполняется — фиксируется только контракт узла.
    """

    node_id: str
    label: str
    props: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


# Registry: stage-boundary name → handoff model (§23.2). Order follows Step 4→7 (§9.2).
HANDOFF_MODELS: dict[str, type[CamelModel]] = {
    "chunk": ChunkHandoff,
    "extraction": ExtractionHandoff,
    "normalization": NormalizationHandoff,
    "er": ERHandoff,
    "upsert": UpsertHandoff,
}


def _format_errors(exc: ValidationError) -> list[str]:
    """Flatten a pydantic ``ValidationError`` to ``["field.path: message", ...]``."""
    out: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        out.append(f"{loc}: {err['msg']}")
    return out


def validate_handoff(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a handoff ``payload`` against the schema for ``stage`` (§23.2).

    Диспетчер по :data:`HANDOFF_MODELS`. Принимает как snake_case, так и camelCase ключи
    (``populate_by_name=True``). Возвращает ``{"valid": bool, "errors": list[str]}``:

    * неизвестный ``stage`` → ``valid=False`` и одна ошибка с перечнем допустимых стыков;
    * ошибка валидации → ``valid=False`` и по строке на каждое нарушение (``field: message``);
    * успех → ``valid=True`` и пустой ``errors``.
    """
    model = HANDOFF_MODELS.get(stage)
    if model is None:
        known = ", ".join(sorted(HANDOFF_MODELS))
        return {"valid": False, "errors": [f"unknown stage: {stage!r} (known: {known})"]}
    try:
        model.model_validate(payload)
    except ValidationError as exc:
        return {"valid": False, "errors": _format_errors(exc)}
    return {"valid": True, "errors": []}


__all__ = [
    "HANDOFF_MODELS",
    "ChunkHandoff",
    "ERHandoff",
    "ExtractionHandoff",
    "NormalizationHandoff",
    "UpsertHandoff",
    "validate_handoff",
]
