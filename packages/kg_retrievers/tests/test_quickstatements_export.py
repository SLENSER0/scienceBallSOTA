"""Tests for Wikidata QuickStatements V1 export (§22)."""

from __future__ import annotations

from kg_retrievers.quickstatements_export import (
    QsStatement,
    claim_statement,
    create_item,
    label_statement,
    to_qs,
)


def test_create_item_is_literal_create() -> None:
    assert create_item() == "CREATE"


def test_label_statement_en_predicate_and_quoted_value() -> None:
    st = label_statement("LAST", "en", "Al2O3")
    assert st.predicate == "Len"
    assert st.value == '"Al2O3"'
    assert st.is_label is True
    assert st.subject == "LAST"


def test_claim_entity_target_is_bare() -> None:
    st = claim_statement("Q1", "P31", "Q5")
    assert st.value == "Q5"
    assert st.is_label is False
    # Exactly two tabs -> three columns, no quotes on the Q-target.
    assert st.as_line() == "Q1\tP31\tQ5"
    assert st.as_line().count("\t") == 2


def test_claim_string_literal_is_quoted() -> None:
    st = claim_statement("Q1", "P1476", "Corundum", is_string=True)
    assert st.value == '"Corundum"'
    assert st.as_line() == 'Q1\tP1476\t"Corundum"'


def test_to_qs_joins_lines_with_two_tabs_each() -> None:
    stmts = [
        label_statement("LAST", "en", "Alumina"),
        claim_statement("LAST", "P31", "Q11344"),
    ]
    text = to_qs(stmts)
    lines = text.split("\n")
    assert lines == ['LAST\tLen\t"Alumina"', "LAST\tP31\tQ11344"]
    for line in lines:
        assert line.count("\t") == 2


def test_embedded_double_quote_is_escaped_in_label() -> None:
    st = label_statement("LAST", "en", 'the "best" oxide')
    assert st.value == '"the \\"best\\" oxide"'
    assert '\\"best\\"' in st.as_line()


def test_to_qs_empty_is_empty_string() -> None:
    assert to_qs([]) == ""


def test_as_dict_reflects_constructor() -> None:
    lab = QsStatement("Q1", "Len", '"x"', True)
    assert lab.as_dict()["is_label"] is True
    assert lab.as_dict() == {
        "subject": "Q1",
        "predicate": "Len",
        "value": '"x"',
        "is_label": True,
    }
    claim = QsStatement("Q1", "P31", "Q5", False)
    assert claim.as_dict()["is_label"] is False


def test_frozen_dataclass_is_immutable() -> None:
    st = claim_statement("Q1", "P31", "Q5")
    try:
        st.subject = "Q2"  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:  # pragma: no cover
        raise AssertionError("QsStatement must be frozen")
