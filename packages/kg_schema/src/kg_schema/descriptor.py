"""§3.17 — machine-readable schema descriptor for Graph Explorer + contract tests.

Полный машиночитаемый дескриптор схемы (*machine-readable schema descriptor*): один
плоский, детерминированный снимок онтологии, который отдаётся фронтенду Graph Explorer
и служит эталоном для contract-тестов на CI (§3.17). Дескриптор перечисляет:

* **labels** — каждую метку узла (*node label*): все ``NodeLabel`` + провенанс-узлы
  ``RunLabel`` (§8.1 / §8.2), в порядке объявления, без дублей.
* **relationships** — каждую декларативную сигнатуру ребра ``(from, rel, to)`` из
  :data:`kg_schema.relationships.EDGE_SCHEMA` (§3.5); виртуальная метка ``Entity``
  сохраняется как есть (её раскрывает :func:`kg_schema.relationships.is_valid_edge`).
* **enums** — набор значений каждого контролируемого словаря (*controlled vocabulary*)
  из :mod:`kg_schema.enums` (§3.2 / §8.3 / §24), ключи — стабильные snake_case имена
  (``domain`` → :class:`MetallurgicalDomain`, ``verification_level`` →
  :class:`VerificationLevel`).
* **version** — версия схемы, действующая на момент снимка (§3.15 / §23.4), по умолчанию
  :data:`kg_schema.run_metadata.DEFAULT_SCHEMA_VERSION`.

Модуль НИЧЕГО не переопределяет: он читает ``NodeLabel`` / ``RunLabel`` / ``EDGE_SCHEMA``
и enum-классы из уже существующих модулей и лишь проецирует их в сериализуемую форму.
:meth:`SchemaDescriptor.as_dict` даёт канонический словарь, :meth:`SchemaDescriptor.to_json`
— его JSON (round-trip: ``json.loads(desc.to_json()) == desc.as_dict()``).

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()``, в ``RETURN`` идут только базовые колонки. Дескриптор описывает форму схемы
(метки/рёбра/словари), а не хранит данные графа, поэтому этого ограничения не касается.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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
from kg_schema.labels import NodeLabel, RunLabel
from kg_schema.relationships import EDGE_SCHEMA
from kg_schema.run_metadata import DEFAULT_SCHEMA_VERSION

# Stable snake_case key → enum class (§3.17). Keys are the machine-readable names the
# Graph Explorer and contract tests address enums by; keep them stable across releases.
ENUM_REGISTRY: dict[str, type[StrEnum]] = {
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


@dataclass(frozen=True)
class RelationshipSignature:
    """One declarative ``(from, rel, to)`` edge signature (§3.5 / §3.17).

    ``from_label`` / ``to_label`` are node labels (or the virtual super-label
    ``Entity``); ``rel`` is a :class:`kg_schema.relationships.RelType` value. All three
    are plain strings so the signature is JSON- and frontend-friendly.
    """

    from_label: str
    rel: str
    to_label: str

    def as_dict(self) -> dict[str, str]:
        """Serialise to ``{"from": ..., "rel": ..., "to": ...}`` (§3.17).

        Uses the JSON key ``from`` (a Python keyword) rather than the field name
        ``from_label`` so the payload reads naturally for the Graph Explorer.
        """
        return {"from": self.from_label, "rel": self.rel, "to": self.to_label}


@dataclass(frozen=True)
class SchemaDescriptor:
    """Immutable machine-readable snapshot of the KG schema (§3.17).

    Attributes
    ----------
    labels:
        Every node label — ``NodeLabel`` followed by ``RunLabel``, in declaration
        order, deduplicated (§8.1 / §8.2).
    relationships:
        Every declarative ``(from, rel, to)`` signature from ``EDGE_SCHEMA`` (§3.5),
        one :class:`RelationshipSignature` per entry, order preserved.
    enums:
        Controlled-vocabulary value sets keyed by :data:`ENUM_REGISTRY` name; each
        value is the ordered tuple of the enum's string values (§3.2 / §8.3).
    version:
        Schema version in force for this snapshot (§3.15 / §23.4).
    """

    labels: tuple[str, ...]
    relationships: tuple[RelationshipSignature, ...]
    enums: dict[str, tuple[str, ...]]
    version: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the canonical ``{labels, relationships, enums, version}`` dict.

        ``labels`` becomes a list, ``relationships`` a list of ``{from, rel, to}``
        dicts, ``enums`` a fresh ``dict`` of lists (copied so callers cannot mutate the
        frozen descriptor through it). Round-trips through :meth:`to_json` (§3.17).
        """
        return {
            "labels": list(self.labels),
            "relationships": [r.as_dict() for r in self.relationships],
            "enums": {name: list(values) for name, values in self.enums.items()},
            "version": self.version,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return :meth:`as_dict` as a JSON string (§3.17).

        ``ensure_ascii=False`` keeps any RU/EN labels readable; key order is preserved
        (``sort_keys=False``) so the payload is stable and diff-friendly for the
        frontend and contract tests. ``json.loads(desc.to_json())`` equals
        ``desc.as_dict()``.
        """
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=indent, sort_keys=False)


def build_schema_descriptor(*, version: str = DEFAULT_SCHEMA_VERSION) -> SchemaDescriptor:
    """Build the full :class:`SchemaDescriptor` from the live schema (§3.17).

    Reads ``NodeLabel`` / ``RunLabel`` (labels), ``EDGE_SCHEMA`` (relationship
    signatures) and :data:`ENUM_REGISTRY` (enum value sets); edits nothing. The
    ``version`` defaults to :data:`DEFAULT_SCHEMA_VERSION` but may be pinned by the
    caller (e.g. to stamp a migration snapshot, §23.4).
    """
    labels = tuple(label.value for label in NodeLabel) + tuple(label.value for label in RunLabel)
    relationships = tuple(
        RelationshipSignature(str(from_label), str(rel), str(to_label))
        for from_label, rel, to_label in EDGE_SCHEMA
    )
    enums = {
        name: tuple(member.value for member in enum_cls) for name, enum_cls in ENUM_REGISTRY.items()
    }
    return SchemaDescriptor(
        labels=labels, relationships=relationships, enums=enums, version=version
    )


__all__ = [
    "ENUM_REGISTRY",
    "RelationshipSignature",
    "SchemaDescriptor",
    "build_schema_descriptor",
]
