"""Тесты агрегатов карточки сущности ``GET /entities/{id}`` (§14.5).

Tests for the reusable entity-detail aggregator: relation counting, missing-field
detection, camelCase ``as_dict`` and the ``verified``/``confidence``/
``review_status``/``evidence_count`` defaults.
"""

from __future__ import annotations

from api_gateway.entity_detail_aggregates import EntityAggregates, compute_aggregates

# Обязательные поля карточки сущности для тестов — required card fields (§14.5).
REQUIRED = ("name", "type", "description")


def _edges(n: int) -> list[dict[str, str]]:
    """n простых рёбер-заглушек — n stub edge mappings for counting."""
    return [{"id": f"e{i}"} for i in range(n)]


def test_relation_count_is_sum_of_in_and_out() -> None:
    """(1) relation_count == len(in_edges) + len(out_edges)."""
    in_edges = _edges(3)
    out_edges = _edges(2)
    agg = compute_aggregates(
        {"name": "N", "type": "T", "description": "D"},
        in_edges,
        out_edges,
        required_fields=REQUIRED,
    )
    assert agg.relation_count == len(in_edges) + len(out_edges)
    assert agg.relation_count == 5


def test_absent_required_field_is_missing() -> None:
    """(2) обязательное поле отсутствует в узле → в missing_fields."""
    agg = compute_aggregates(
        {"name": "N", "type": "T"},  # description отсутствует / absent
        [],
        [],
        required_fields=REQUIRED,
    )
    assert "description" in agg.missing_fields


def test_empty_string_required_field_is_missing() -> None:
    """(3) обязательное поле со значением '' → в missing_fields."""
    agg = compute_aggregates(
        {"name": "N", "type": "T", "description": ""},
        [],
        [],
        required_fields=REQUIRED,
    )
    assert "description" in agg.missing_fields


def test_none_required_field_is_missing() -> None:
    """None-значение обязательного поля также трактуется как недостающее."""
    agg = compute_aggregates(
        {"name": "N", "type": "T", "description": None},
        [],
        [],
        required_fields=REQUIRED,
    )
    assert "description" in agg.missing_fields


def test_present_required_field_not_missing() -> None:
    """(4) обязательное поле с непустым значением → не в missing_fields."""
    agg = compute_aggregates(
        {"name": "N", "type": "T", "description": "real value"},
        [],
        [],
        required_fields=REQUIRED,
    )
    assert "description" not in agg.missing_fields
    assert agg.missing_fields == ()


def test_verified_defaults_false() -> None:
    """(5) verified по умолчанию False, когда узел не содержит 'verified'."""
    agg = compute_aggregates({"name": "N"}, [], [], required_fields=())
    assert agg.verified is False


def test_verified_reads_node_value() -> None:
    """verified читается из узла, когда присутствует."""
    agg = compute_aggregates({"verified": True}, [], [], required_fields=())
    assert agg.verified is True


def test_confidence_defaults_zero() -> None:
    """(6) confidence по умолчанию 0.0, когда отсутствует."""
    agg = compute_aggregates({"name": "N"}, [], [], required_fields=())
    assert agg.confidence == 0.0


def test_confidence_reads_node_value() -> None:
    """confidence читается и приводится к float."""
    agg = compute_aggregates({"confidence": 0.82}, [], [], required_fields=())
    assert agg.confidence == 0.82


def test_as_dict_evidence_count_from_count_field() -> None:
    """(7a) as_dict()['evidenceCount'] отражает node['evidence_count']."""
    agg = compute_aggregates({"evidence_count": 7}, [], [], required_fields=())
    assert agg.as_dict()["evidenceCount"] == 7


def test_as_dict_evidence_count_from_evidence_list() -> None:
    """(7b) as_dict()['evidenceCount'] отражает len(node['evidence'])."""
    node = {"evidence": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    agg = compute_aggregates(node, [], [], required_fields=())
    assert agg.as_dict()["evidenceCount"] == 3


def test_as_dict_evidence_count_defaults_zero() -> None:
    """evidenceCount равен 0, когда ни счётчика, ни списка нет."""
    agg = compute_aggregates({"name": "N"}, [], [], required_fields=())
    assert agg.as_dict()["evidenceCount"] == 0


def test_review_status_defaults_unreviewed() -> None:
    """(8) review_status по умолчанию 'unreviewed', когда отсутствует."""
    agg = compute_aggregates({"name": "N"}, [], [], required_fields=())
    assert agg.review_status == "unreviewed"
    assert agg.as_dict()["reviewStatus"] == "unreviewed"


def test_review_status_reads_node_value() -> None:
    """review_status читается из узла, когда присутствует."""
    agg = compute_aggregates({"review_status": "verified"}, [], [], required_fields=())
    assert agg.review_status == "verified"


def test_as_dict_camelcase_keys_and_shape() -> None:
    """as_dict() эмитит camelCase-ключи §5.3, missingFields — список."""
    node = {
        "name": "Aspirin",
        "type": "",  # пустое → недостающее / empty → missing
        "verified": True,
        "confidence": 0.5,
        "review_status": "in_review",
        "evidence_count": 4,
    }
    agg = compute_aggregates(node, _edges(1), _edges(1), required_fields=REQUIRED)
    d = agg.as_dict()
    assert set(d) == {
        "evidenceCount",
        "relationCount",
        "verified",
        "confidence",
        "reviewStatus",
        "missingFields",
    }
    assert d["evidenceCount"] == 4
    assert d["relationCount"] == 2
    assert d["verified"] is True
    assert d["confidence"] == 0.5
    assert d["reviewStatus"] == "in_review"
    assert isinstance(d["missingFields"], list)
    assert d["missingFields"] == ["type", "description"]


def test_frozen_immutability() -> None:
    """EntityAggregates неизменяем — попытка присвоения даёт исключение."""
    agg = compute_aggregates({"name": "N"}, [], [], required_fields=())
    assert isinstance(agg, EntityAggregates)
    try:
        agg.verified = True  # type: ignore[misc]
    except Exception as exc:  # проверяем факт неизменяемости / immutability check
        assert exc.__class__.__name__ in {"FrozenInstanceError", "AttributeError"}
    else:  # pragma: no cover — frozen должен запрещать присваивание
        raise AssertionError("EntityAggregates must be immutable")


def test_bool_evidence_count_not_treated_as_count() -> None:
    """Булев 'evidence_count' игнорируется и падает на список/0."""
    node = {"evidence_count": True, "evidence": [{"id": "a"}]}
    agg = compute_aggregates(node, [], [], required_fields=())
    assert agg.evidence_count == 1
