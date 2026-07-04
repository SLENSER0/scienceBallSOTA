"""Tests for §6.8 materials NER + MatSciBERT embeddings + GLiNER fusion.

Acceptance criteria (§6.8):
* MatSciBERT embedder returns a correctly-shaped vector for a *batch*.
* The MatEntityRecognition wrapper implements the ``Extractor`` (``NerBackend``)
  protocol and extracts materials mentions with valid evidence spans.
* GLiNER ⊕ MatEntityRecognition fusion creates **no duplicates** on full span
  overlap.
"""

from __future__ import annotations

from kg_extractors.materials_ner import (
    MATSCIBERT_HIDDEN,
    MatEntityRecognizer,
    MatSciBertEmbedder,
    fuse_mentions,
    fuse_text,
)
from kg_extractors.ml_ner import NerBackend, NerSpan

_SENT = (
    "Никелевый сплав ХН77ТЮР подвергали электроэкстракции при плотности тока "
    "250 А/м². Твёрдость образца достигла 320 HV, предел прочности 780 МПа. "
    "Фазовый состав Al2O3 определён на дифрактометре."
)


def test_matscibert_embed_batch_shape() -> None:
    """Embedder returns one hidden_size-dim vector per text in the batch."""
    emb = MatSciBertEmbedder()
    report = emb.embed_batch(["никель медь железо", "сплав титан хром", "Al2O3 TiO2"])
    assert report.n_texts == 3
    assert report.dim == MATSCIBERT_HIDDEN
    assert len(report.vectors) == 3
    for vec in report.vectors:
        assert len(vec) == MATSCIBERT_HIDDEN
    # L2-normalised (real or fallback) → norm ≈ 1 for non-empty text.
    norm = sum(v * v for v in report.vectors[0]) ** 0.5
    assert 0.9 <= norm <= 1.1


def test_mat_entity_recognizer_is_extractor_with_spans() -> None:
    """Wrapper satisfies the NerBackend protocol and returns anchored spans."""
    rec = MatEntityRecognizer()
    assert isinstance(rec, NerBackend)  # runtime_checkable Protocol
    spans = rec.extract(_SENT)
    assert len(spans) >= 1
    for s in spans:
        assert isinstance(s, NerSpan)
        # Evidence span invariant: surface text == source[start:end].
        assert _SENT[s.start : s.end] == s.text
        assert 0 <= s.start < s.end <= len(_SENT)
        assert 0.0 <= s.score <= 1.0


def test_fusion_no_duplicate_on_full_overlap() -> None:
    """Fully overlapping GLiNER + MatEntity spans collapse to one mention."""
    a = [NerSpan("ХН77ТЮР", "alloy", 16, 23, 0.9)]
    b = [NerSpan("ХН77ТЮР", "material", 16, 23, 0.8)]
    fused = fuse_mentions(a, b)
    assert len(fused) == 1
    fm = fused[0]
    assert fm.char_start == 16 and fm.char_end == 23
    assert set(fm.sources) == {"gliner", "mat-entity"}
    assert fm.as_dict()["agreement"] is True
    # Agreement lifts confidence above either input (noisy-OR).
    assert fm.score >= max(0.9, 0.8)
    # Stronger span wins the label.
    assert fm.label == "alloy"


def test_fusion_keeps_disjoint_mentions() -> None:
    """Non-overlapping spans are preserved (no accidental merge)."""
    a = [NerSpan("никель", "chemical_element", 0, 6, 0.8)]
    b = [NerSpan("твёрдость", "property", 40, 49, 0.7)]
    fused = fuse_mentions(a, b)
    assert len(fused) == 2


def test_fuse_text_end_to_end() -> None:
    """fuse_text runs GLiNER ⊕ MatEntity and yields anchored fused mentions."""
    rep = fuse_text(_SENT)
    assert rep.n_fused >= 1
    assert rep.mat_backend in ("mat-entity", "lexicon-fallback")
    assert rep.gliner_backend in ("gliner", "rule")
    # Fused count never exceeds the naive sum (dedup can only shrink).
    assert rep.n_fused <= rep.n_gliner + rep.n_mat
    for m in rep.mentions:
        assert _SENT[m["char_start"] : m["char_end"]] == m["text"]
