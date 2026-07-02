"""Per-type feature engineering: raw mention dict -> Splink feature row (§8.3).

Each ``build_*_row`` is pure and deterministic so ``build_er_frame`` produces a
stable DataFrame the Splink models and blocking rules consume. Column names here
must match ``kg_er.blocking.BLOCKING_RULES`` and the per-type model comparisons.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kg_er.comparisons import composition, text


def _first_token(value: str | None) -> str:
    cleaned = text.clean_text(value)
    return cleaned.split()[0] if cleaned else ""


def build_material_row(rec: Mapping[str, Any]) -> dict[str, Any]:
    name = rec.get("name") or rec.get("alias_text") or ""
    formula = rec.get("formula") or rec.get("normalized_formula") or ""
    comp = composition.normalize_formula(formula)
    return {
        "unique_id": rec["unique_id"],
        "name_clean": text.clean_text(name),
        "normalized_formula": comp.reduced_formula if comp else "",
        "element_key": comp.element_key if comp else "",
        "element_set": " ".join(sorted(comp.element_set)) if comp else "",
        "alloy_family": text.clean_text(rec.get("alloy_family")),
        "designation_code": text.designation_code(rec.get("designation") or name),
    }


def build_equipment_row(rec: Mapping[str, Any]) -> dict[str, Any]:
    name = rec.get("name") or ""
    return {
        "unique_id": rec["unique_id"],
        "name_clean": text.clean_text(name),
        "manufacturer": text.clean_text(rec.get("manufacturer")),
        "model_code": text.clean_text(rec.get("model") or rec.get("model_code")),
        "equipment_class": text.clean_text(rec.get("equipment_class")),
    }


def build_person_row(rec: Mapping[str, Any]) -> dict[str, Any]:
    name = rec.get("name") or ""
    given, family, initials = text.split_person_name(name)
    return {
        "unique_id": rec["unique_id"],
        "name_clean": text.clean_text(name),
        "given_name": given,
        "family_name": family or _first_token(name),
        "given_initial": (given[:1] or initials[:1]),
        "initials": initials,
        "orcid": (rec.get("orcid") or "").strip(),
        "email_domain": text.email_domain(rec.get("email")),
    }


def build_lab_row(rec: Mapping[str, Any]) -> dict[str, Any]:
    name = rec.get("name") or ""
    org = rec.get("org") or name
    return {
        "unique_id": rec["unique_id"],
        "name_clean": text.clean_text(name),
        "org": text.clean_text(org),
        "org_token": _first_token(org),
        "city": text.clean_text(rec.get("city")),
        "country": text.clean_text(rec.get("country")),
        "parent_institution": text.clean_text(rec.get("parent_institution")),
    }


BUILDERS = {
    "Material": build_material_row,
    "Alloy": build_material_row,
    "Equipment": build_equipment_row,
    "Person": build_person_row,
    "Lab": build_lab_row,
    "ResearchTeam": build_lab_row,
}


def build_row(entity_type: str, rec: Mapping[str, Any]) -> dict[str, Any]:
    if entity_type not in BUILDERS:
        raise KeyError(f"no feature builder for {entity_type!r}")
    return BUILDERS[entity_type](rec)
