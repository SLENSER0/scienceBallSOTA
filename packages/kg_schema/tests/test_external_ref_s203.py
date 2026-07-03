"""§20.3 — tests for the external-system reference node model (:mod:`external_ref_s203`).

Hand-checkable assertions against concrete expected values: deterministic node id,
order-independent + value-sensitive payload hashing, the seven-field serialisation, the
system allow-list guard, and the ``HAS_EXTERNAL_REF`` edge shape.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from kg_schema.external_ref_s203 import (
    VALID_SYSTEMS,
    ExternalRef,
    compute_payload_hash,
    has_external_ref_edge,
    make_external_ref,
)


def test_valid_systems_exact_set() -> None:
    """The controlled vocabulary is exactly the six documented systems (§20.3)."""
    expected = {"elabftw", "openbis", "materials_project", "matkg", "matscholar", "propnet"}
    assert set(VALID_SYSTEMS) == expected


def test_make_external_ref_id_is_literal_system_and_external_id() -> None:
    """``id`` is ``extref:{system}:{external_id}`` verbatim (§20.3)."""
    ref = make_external_ref("elabftw", "exp:12", {"a": 1})
    assert ref.id == "extref:elabftw:exp:12"
    assert ref.system == "elabftw"
    assert ref.external_id == "exp:12"


def test_make_external_ref_rejects_unknown_system() -> None:
    """An out-of-vocabulary system raises ``ValueError`` (§20.3)."""
    with pytest.raises(ValueError):
        make_external_ref("bogus", "x", {})


def test_make_external_ref_sets_payload_hash() -> None:
    """``payload_hash`` equals :func:`compute_payload_hash` of the payload (§20.3)."""
    payload = {"a": 1, "b": 2}
    ref = make_external_ref("openbis", "obj/7", payload)
    assert ref.payload_hash == compute_payload_hash(payload)


def test_make_external_ref_optional_fields_default_empty() -> None:
    """Unset url/version/fetched_at default to empty strings (§20.3)."""
    ref = make_external_ref("propnet", "p1", {})
    assert ref.external_url == ""
    assert ref.system_version == ""
    assert ref.fetched_at == ""


def test_make_external_ref_passes_optional_fields_through() -> None:
    """Provided optional fields are stored verbatim (§20.3)."""
    ref = make_external_ref(
        "materials_project",
        "mp-149",
        {"formula": "Si"},
        external_url="https://materialsproject.org/materials/mp-149",
        system_version="2024.1",
        fetched_at="2026-07-03T00:00:00Z",
    )
    assert ref.external_url == "https://materialsproject.org/materials/mp-149"
    assert ref.system_version == "2024.1"
    assert ref.fetched_at == "2026-07-03T00:00:00Z"


def test_compute_payload_hash_is_order_independent() -> None:
    """Key order does not change the digest (§20.3)."""
    assert compute_payload_hash({"a": 1, "b": 2}) == compute_payload_hash({"b": 2, "a": 1})


def test_compute_payload_hash_is_value_sensitive() -> None:
    """Different values yield different digests (§20.3)."""
    assert compute_payload_hash({"a": 1}) != compute_payload_hash({"a": 2})


def test_compute_payload_hash_matches_reference_sha256() -> None:
    """The digest is the sha256 hex of canonical ``sort_keys=True`` JSON (§20.3)."""
    payload = {"b": 2, "a": 1}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    assert compute_payload_hash(payload) == expected
    assert len(compute_payload_hash(payload)) == 64


def test_as_dict_shape_and_system_value() -> None:
    """``as_dict`` carries exactly seven fields with the right system (§20.3)."""
    ref = make_external_ref("elabftw", "exp:12", {"a": 1})
    d = ref.as_dict()
    assert d["system"] == "elabftw"
    assert len(d) == 7
    assert set(d) == {
        "id",
        "system",
        "external_id",
        "external_url",
        "system_version",
        "fetched_at",
        "payload_hash",
    }


def test_as_dict_round_trips_through_constructor() -> None:
    """``ExternalRef(**ref.as_dict())`` reconstructs an equal node (§20.3)."""
    ref = make_external_ref("matkg", "k42", {"x": [1, 2, 3]})
    assert ExternalRef(**ref.as_dict()) == ref


def test_external_ref_is_frozen() -> None:
    """The dataclass is immutable (§20.3)."""
    ref = make_external_ref("matscholar", "s9", {})
    with pytest.raises(FrozenInstanceError):
        ref.system = "propnet"  # type: ignore[misc]


def test_has_external_ref_edge_shape() -> None:
    """The edge is ``HAS_EXTERNAL_REF`` from entity to ref (§20.3)."""
    edge = has_external_ref_edge("material:x", "extref:y")
    assert edge["type"] == "HAS_EXTERNAL_REF"
    assert edge == {"type": "HAS_EXTERNAL_REF", "from": "material:x", "to": "extref:y"}
