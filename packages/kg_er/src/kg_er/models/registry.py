"""Single entry point to per-type Splink specs (§8.5 registry)."""

from __future__ import annotations

from kg_er.models.base import ModelSpec
from kg_er.models.equipment import equipment_spec
from kg_er.models.lab import lab_spec
from kg_er.models.material import material_spec
from kg_er.models.person import person_spec

_FACTORIES = {
    "Material": material_spec,
    "Alloy": material_spec,
    "Equipment": equipment_spec,
    "Person": person_spec,
    "Lab": lambda: lab_spec("Lab"),
    "ResearchTeam": lambda: lab_spec("ResearchTeam"),
}

SUPPORTED_TYPES = tuple(_FACTORIES)


def get_model(entity_type: str) -> ModelSpec:
    """Return the :class:`ModelSpec` for *entity_type* (§8.5)."""
    if entity_type not in _FACTORIES:
        raise KeyError(f"no ER model for entity type {entity_type!r}; supported={SUPPORTED_TYPES}")
    return _FACTORIES[entity_type]()
