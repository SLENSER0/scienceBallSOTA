"""§3.20 — machine-readable enum catalog (controlled vocabularies as data).

Плоский детерминированный каталог контролируемых словарей (*controlled vocabularies*):
каждый enum из :mod:`kg_schema.enums` проецируется в стабильное snake_case имя → кортеж
строковых значений (§3.2 / §8.3 / §24). Каталог отдаётся агентам/фронтенду и служит
эталоном для contract-тестов; он НИЧЕГО не переопределяет — лишь читает enum-классы.

The catalog is data, not behaviour: :data:`ENUM_CATALOG` maps a stable machine name to the
ordered tuple of an enum's string values; :func:`catalog` returns a defensive copy,
:func:`values_of` looks one up (unknown name → empty tuple ``()``), and :func:`to_json`
serialises the whole catalog. Round-trip holds: ``json.loads(to_json())`` equals
``{name: list(values) for name, values in catalog().items()}``.

Требование §3.20 — покрыть ``domain`` / ``verification_level`` / ``gap_type`` /
``evidence_strength``; здесь покрыты они и остальные словари :mod:`kg_schema.enums`.

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()``, в ``RETURN`` идут только базовые колонки. Каталог описывает допустимые
значения словарей (форму схемы), а не данные графа, поэтому этого ограничения не касается.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from kg_schema.enums import (
    Atmosphere,
    ConfidentialityLevel,
    CurationAction,
    CurationTargetType,
    EffectDirection,
    EvidenceStrength,
    GapType,
    MatchDecision,
    MaterialClass,
    MetallurgicalDomain,
    PracticeGeography,
    ProcessingOperation,
    PropertyClass,
    ReviewStatus,
    Role,
    SourceDocType,
    SourceType,
    VerificationLevel,
)


@dataclass(frozen=True)
class EnumEntry:
    """Один словарь каталога: стабильное имя + упорядоченные значения (§3.20).

    One catalog vocabulary — a stable snake_case ``name`` and the ordered tuple of the
    enum's string ``values``. Immutable, so it is safe to share across callers/threads.
    """

    name: str
    values: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        """Serialise to ``{"name": ..., "values": [...]}`` (values as a JSON list)."""
        return {"name": self.name, "values": list(self.values)}


# Stable snake_case name → enum class (§3.20). These machine names are how agents and
# contract tests address a vocabulary; keep them stable across releases (§3.2 / §8.3).
_ENUM_REGISTRY: dict[str, type[StrEnum]] = {
    "gap_type": GapType,
    "review_status": ReviewStatus,
    "source_type": SourceType,
    "effect_direction": EffectDirection,
    "match_decision": MatchDecision,
    "curation_action": CurationAction,
    "curation_target_type": CurationTargetType,
    "material_class": MaterialClass,
    "property_class": PropertyClass,
    "processing_operation": ProcessingOperation,
    "atmosphere": Atmosphere,
    "domain": MetallurgicalDomain,
    "practice_geography": PracticeGeography,
    "evidence_strength": EvidenceStrength,
    "verification_level": VerificationLevel,
    "source_doc_type": SourceDocType,
    "role": Role,
    "confidentiality_level": ConfidentialityLevel,
}

# The catalog proper: machine name → ordered tuple of the enum's string values (§3.20).
# Built once at import; insertion order mirrors ``_ENUM_REGISTRY`` for determinism.
ENUM_CATALOG: dict[str, tuple[str, ...]] = {
    name: tuple(member.value for member in enum_cls) for name, enum_cls in _ENUM_REGISTRY.items()
}

# The same catalog as immutable :class:`EnumEntry` records, in the same order.
ENUM_ENTRIES: tuple[EnumEntry, ...] = tuple(
    EnumEntry(name, values) for name, values in ENUM_CATALOG.items()
)


def catalog() -> dict[str, tuple[str, ...]]:
    """Return a fresh copy of :data:`ENUM_CATALOG` (name → ordered value tuple, §3.20).

    Отдаётся копия верхнего уровня, поэтому изменение результата не затрагивает
    :data:`ENUM_CATALOG`; значения — неизменяемые кортежи. Deterministic and stable.
    """
    return dict(ENUM_CATALOG)


def values_of(name: str) -> tuple[str, ...]:
    """Return the ordered values for enum ``name`` (§3.20); unknown name → ``()``.

    Неизвестное имя даёт пустой кортеж (не бросает), чтобы вызывающий код мог безопасно
    проверять принадлежность значения словарю без обработки исключений.
    """
    return ENUM_CATALOG.get(name, ())


def to_json(*, indent: int | None = None) -> str:
    """Serialise the whole catalog to JSON: name → list of values (§3.20).

    ``ensure_ascii=False`` keeps RU/EN-friendly output; ``sort_keys=False`` preserves the
    registry order so the payload is stable and diff-friendly. Round-trip:
    ``json.loads(to_json()) == {n: list(v) for n, v in catalog().items()}``.
    """
    payload = {name: list(values) for name, values in ENUM_CATALOG.items()}
    return json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=False)


__all__ = [
    "ENUM_CATALOG",
    "ENUM_ENTRIES",
    "EnumEntry",
    "catalog",
    "to_json",
    "values_of",
]
