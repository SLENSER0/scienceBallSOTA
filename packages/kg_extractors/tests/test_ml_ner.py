"""Tests for the ML-NER adapter + rule fallback (§6.7).

``gliner`` is intentionally NOT installed, so ``get_ner_backend('auto')`` must
fall back to the deterministic :class:`RuleNerBackend`, and importing the module
must never pull in the optional dependency.
"""

from __future__ import annotations

import sys

from kg_extractors.ml_ner import (
    GlinerNerBackend,
    NerBackend,
    NerSpan,
    RuleNerBackend,
    get_ner_backend,
)

# RU metallurgy sample: никель (nickel), католит (catholyte),
# электроэкстракция (electrowinning), скорость потока (flow velocity).
SAMPLE = (
    "Никель и католит изучены на переделе. Электроэкстракция обеспечивает "
    "высокую скорость потока при плотности тока 250 А/м²."
)


def _texts(spans: list[NerSpan]) -> set[str]:
    return {s.text.lower() for s in spans}


def test_rule_backend_extracts_nickel_and_electrowinning() -> None:
    spans = RuleNerBackend().extract(SAMPLE)
    texts = _texts(spans)
    assert "никель" in texts  # nickel (nominative, capitalised in text)
    assert "электроэкстракция" in texts  # electrowinning
    # labels come from the taxonomy node_type mapping
    labels = {s.text.lower(): s.label for s in spans}
    assert labels["никель"] == "MATERIAL"
    assert labels["электроэкстракция"] == "PROCESS"


def test_ner_span_offsets_within_text() -> None:
    spans = RuleNerBackend().extract(SAMPLE)
    assert spans, "expected at least one span"
    for s in spans:
        assert 0 <= s.start < s.end <= len(SAMPLE)
        # offsets are anchored: the slice equals the surface text exactly
        assert SAMPLE[s.start : s.end] == s.text


def test_get_ner_backend_auto_is_working_rule_fallback() -> None:
    backend = get_ner_backend("auto")
    # gliner is not installed → auto must yield the rule backend
    assert isinstance(backend, RuleNerBackend)
    assert isinstance(backend, NerBackend)  # satisfies the Protocol
    spans = backend.extract(SAMPLE)
    assert "никель" in _texts(spans)


def test_get_ner_backend_rule_explicit() -> None:
    backend = get_ner_backend("rule")
    assert isinstance(backend, RuleNerBackend)
    assert backend.name == "rule"
    assert backend.extract(SAMPLE)  # produces spans


def test_empty_and_whitespace_text_returns_empty() -> None:
    backend = get_ner_backend("auto")
    assert backend.extract("") == []
    assert backend.extract("   \n\t ") == []


def test_all_labels_non_empty() -> None:
    spans = RuleNerBackend().extract(SAMPLE)
    assert spans
    assert all(s.label and s.label.strip() for s in spans)


def test_scores_within_unit_interval() -> None:
    spans = RuleNerBackend().extract(SAMPLE)
    assert spans
    assert all(0.0 <= s.score <= 1.0 for s in spans)


def test_unknown_backend_name_raises() -> None:
    try:
        get_ner_backend("transformer")
    except ValueError as exc:
        assert "transformer" in str(exc)
    else:  # pragma: no cover - must raise
        raise AssertionError("expected ValueError for unknown backend name")


def test_ner_span_as_dict_roundtrip() -> None:
    span = NerSpan(text="никель", label="MATERIAL", start=0, end=6, score=0.7)
    assert span.as_dict() == {
        "text": "никель",
        "label": "MATERIAL",
        "start": 0,
        "end": 6,
        "score": 0.7,
    }


def test_importing_module_does_not_import_gliner() -> None:
    # The optional dependency must stay unimported at module load time (§6.7),
    # and it is not installed in this environment at all.
    assert "gliner" not in sys.modules
    assert GlinerNerBackend.name == "gliner"  # class is import-safe to reference
