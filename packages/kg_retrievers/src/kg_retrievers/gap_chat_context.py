"""'Discuss this gap' → seed chat context (§17.14). / Обсудить пробел → контекст чата.

Section 17.14 puts a **«Обсудить этот пробел» / "Discuss this gap"** button next
to every Gap finding. Pressing it must open the chat pre-seeded with a natural
question *about that specific gap* and with the relevant retrieval filters
already applied, so the analyst can start the conversation without re-typing the
material / property under discussion.

This module is a *pure builder*: it folds a single gap dict (as produced by the
§11.1 gap scanner — see :class:`kg_schema.enums.GapType`) into a frozen
:class:`GapChatContext`. No store, no I/O, no LLM call — just template selection
and field copying. The container is what the chat UI consumes to prime a fresh
session; :func:`GapChatContext.as_dict` yields the JSON payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_common import get_logger

_log = get_logger("gap_chat_context")

#: Per-gap-type seed-question templates, keyed by the §11.1 :class:`GapType`
#: string values. Each template is a ``str.format`` string over the fields
#: ``entity`` / ``property`` / ``material``; missing fields degrade to a neutral
#: placeholder (see :func:`_fill`). RU/EN kept bilingual per house style.
SEED_TEMPLATES: dict[str, str] = {
    "missing_property_value": (
        "Какое значение свойства «{property}» у «{entity}» и где его найти? "
        "/ What is the value of property '{property}' for '{entity}'?"
    ),
    "missing_baseline": (
        "Какой базовый уровень (baseline) отсутствует у «{entity}»? "
        "/ Which baseline is missing for '{entity}'?"
    ),
    "missing_processing_parameter": (
        "Какие параметры обработки не заданы для «{entity}»? "
        "/ Which processing parameters are missing for '{entity}'?"
    ),
    "missing_equipment": (
        "Какое оборудование не указано для «{entity}»? / Which equipment is missing for '{entity}'?"
    ),
    "missing_unit": (
        "В каких единицах измеряется «{property}» у «{entity}»? "
        "/ In which unit is '{property}' measured for '{entity}'?"
    ),
    "missing_source_span": (
        "Где первоисточник для «{entity}»? / Where is the source span for '{entity}'?"
    ),
    "unverified_claim": (
        "Как проверить непроверенное утверждение о «{entity}»? "
        "/ How can the unverified claim about '{entity}' be verified?"
    ),
    "contradictory_measurements": (
        "Почему измерения «{property}» у «{entity}» противоречат друг другу? "
        "/ Why do the measurements of '{property}' for '{entity}' contradict?"
    ),
    "low_coverage_material": (
        "Почему у материала «{material}» низкое покрытие данными и как его повысить? "
        "/ Why does material '{material}' have low data coverage?"
    ),
    "low_confidence_entity_resolution": (
        "Почему сущность «{entity}» разрешена с низкой уверенностью? "
        "/ Why was entity '{entity}' resolved with low confidence?"
    ),
    "orphan_entity": (
        "С чем должна быть связана изолированная сущность «{entity}»? "
        "/ What should the orphan entity '{entity}' be connected to?"
    ),
    "missing_geography": (
        "К какой географии относится «{entity}»? / Which geography does '{entity}' belong to?"
    ),
    "missing_applicability_condition": (
        "При каких условиях применимости действует «{entity}»? "
        "/ Under which applicability conditions does '{entity}' hold?"
    ),
    "missing_technoeconomic": (
        "Какие технико-экономические данные отсутствуют у «{entity}»? "
        "/ Which techno-economic data are missing for '{entity}'?"
    ),
    "only_foreign_sources": (
        "Есть ли отечественные источники по «{entity}»? "
        "/ Are there domestic sources for '{entity}'?"
    ),
    "no_pilot_data": (
        "Есть ли пилотные данные по «{entity}»? / Is there any pilot data for '{entity}'?"
    ),
}

#: Fallback question used when the gap type is not in :data:`SEED_TEMPLATES`.
_GENERIC_TEMPLATE = (
    "Где пробелы в данных для «{subject}»? / Where are the data gaps for '{subject}'?"
)

#: Neutral placeholder substituted for absent gap fields, keeping the seed
#: question grammatical even when a field is missing.
_MISSING = "—"


@dataclass(frozen=True)
class GapChatContext:
    """Seed context for the §17.14 'Discuss this gap' chat. / Контекст чата по пробелу.

    Immutable payload handed to a fresh chat session:

    * ``seed_question`` — the pre-filled question shown in the composer;
    * ``gap_type`` — the originating §11.1 gap type, passed through verbatim;
    * ``entity_id`` — the gap's subject entity id (or ``None`` if not entity-scoped);
    * ``filters`` — prefilled retrieval filters (``material`` / ``property`` when known);
    * ``gap_ids`` — ids of the gap(s) this conversation is seeded from.
    """

    seed_question: str
    gap_type: str
    entity_id: str | None
    filters: dict = field(default_factory=dict)
    gap_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        """JSON payload for the chat UI. / Полезная нагрузка для интерфейса чата."""
        return {
            "seedQuestion": self.seed_question,
            "gapType": self.gap_type,
            "entityId": self.entity_id,
            "filters": dict(self.filters),
            "gapIds": list(self.gap_ids),
        }


def _first(gap: dict, *keys: str) -> str | None:
    """Return the first present, non-empty value among ``keys``. / Первое значение."""
    for key in keys:
        val = gap.get(key)
        if val not in (None, ""):
            return str(val)
    return None


def _fill(template: str, gap: dict, *, subject: str) -> str:
    """Fill ``template`` from gap fields, degrading missing ones. / Заполнить шаблон."""
    entity = _first(gap, "entity", "entityName", "entityLabel", "name") or subject
    prop = _first(gap, "property", "propertyName", "prop") or _MISSING
    material = _first(gap, "material", "materialName") or subject
    return template.format(entity=entity, property=prop, material=material, subject=subject)


def build_gap_chat_context(gap: dict) -> GapChatContext:
    """Build a §17.14 seed chat context from one gap finding. / Построить контекст чата.

    Аргументы / Arguments:
        gap: one §11.1 gap dict. Recognised fields: ``gapType``/``gap_type`` (the
            §11.1 type), ``id``, ``entityId``, ``entity`` (label), ``property``,
            ``material``, ``description``. All are optional bar sensible defaults.

    Правила / Rules:
        * pick :data:`SEED_TEMPLATES` by gap type, else the generic template;
        * fill the template from the gap's entity / property / material, with the
          gap ``description`` (or entity/material) as the fallback subject;
        * copy ``material`` and ``property`` into ``filters`` **only when present**;
        * carry the gap ``id`` (when any) into ``gap_ids``; ``entity_id`` mirrors
          ``gap['entityId']`` verbatim.

    Возвращает / Returns:
        A frozen :class:`GapChatContext`.
    """
    gap_type = str(gap.get("gapType") or gap.get("gap_type") or "")
    subject = _first(gap, "description", "entity", "material", "entityName", "name") or _MISSING

    template = SEED_TEMPLATES.get(gap_type, _GENERIC_TEMPLATE)
    seed_question = _fill(template, gap, subject=subject)

    filters: dict = {}
    material = _first(gap, "material", "materialName")
    if material is not None:
        filters["material"] = material
    prop = _first(gap, "property", "propertyName", "prop")
    if prop is not None:
        filters["property"] = prop

    entity_id = gap.get("entityId")
    gap_id = gap.get("id")
    gap_ids: tuple[str, ...] = (str(gap_id),) if gap_id not in (None, "") else ()

    _log.debug("gap_chat_context type=%s entity=%s filters=%s", gap_type, entity_id, filters)
    return GapChatContext(
        seed_question=seed_question,
        gap_type=gap_type,
        entity_id=entity_id,
        filters=filters,
        gap_ids=gap_ids,
    )
