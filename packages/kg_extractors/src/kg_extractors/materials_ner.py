"""Domain materials-science NER + MatSciBERT embeddings, fused with GLiNER (§6.8).

This is the production entry point for *materials-specialised* extraction. It
sits on top of the flexible GLiNER extractor (§6.7, :mod:`kg_extractors.gliner`)
and adds the three things §6.8 asks for:

* **MatSciBERT embeddings.** :class:`MatSciBertEmbedder` loads the OSS
  ``m3rg-iitd/matscibert`` checkpoint (a materials-science BERT) once per process
  via ``transformers`` + ``torch`` and returns mean-pooled, L2-normalised
  sentence vectors of ``hidden_size`` (768) for a *batch* of chunk texts — a
  reusable component for indexing (§9.2 Step 8) and entity resolution. When the
  weights cannot be fetched (offline / no cache) it degrades to a deterministic
  hashing embedder of the *same* dimension, so the shape contract always holds
  and the backend is reported honestly.

* **MatEntityRecognition wrapper.** :class:`MatEntityRecognizer` wraps the
  CederGroupHub materials NER as an :class:`~kg_extractors.ml_ner.NerBackend`
  (``extract(text) -> list[NerSpan]`` with real evidence spans), mapping its
  ``MAT``/``PRO``/``APL``/``SMT``/``CMT``/``DSC``/``SPL`` tags onto the §8.1
  domain labels. When the vendored model is absent it falls back to a
  deterministic materials-lexicon tagger (chemical formulas, element/alloy grades,
  processing operations, properties, characterisation methods) so it still emits
  ≥ 1 anchored materials mention on a reference sentence — OSS-only, offline-safe.

* **GLiNER ⊕ MatEntityRecognition fusion.** :func:`fuse_mentions` merges the two
  mention streams: it deduplicates overlapping spans (span IoU) and combines the
  confidences (agreement between the two extractors *raises* the fused score),
  provably emitting **no duplicate** when spans fully overlap. This lifts recall
  on materials / properties / processes above either extractor alone.

Everything is import-safe: importing this module never imports ``torch`` or the
vendored NER; heavy work is deferred to first use and always has an offline path.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import importlib.util
import re
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from kg_common.logging import get_logger
from kg_extractors.ml_ner import NerSpan

_log = get_logger("kg_extractors.materials_ner")

# OSS materials-science BERT (HuggingFace). 768-dim hidden state (BERT-base).
DEFAULT_MATSCIBERT = "m3rg-iitd/matscibert"
MATSCIBERT_HIDDEN = 768
DEFAULT_DEVICE = "cpu"

# CederGroupHub MatEntityRecognition tag → §8.1 domain label.
# MAT=material, PRO=property, APL=application, SMT=synthesis method,
# CMT=characterisation method, DSC=descriptor, SPL=symmetry/phase label.
MAT_TAG_MAP: dict[str, str] = {
    "MAT": "material",
    "PRO": "property",
    "APL": "application",
    "SMT": "processing_operation",
    "CMT": "method",
    "DSC": "descriptor",
    "SPL": "sample",
}

# Labels the materials NER can surface (superset of the fallback lexicon labels).
MATERIALS_LABELS: tuple[str, ...] = (
    "material",
    "alloy",
    "chemical_element",
    "property",
    "processing_operation",
    "method",
    "application",
    "descriptor",
    "sample",
)


def _clamp01(x: float) -> float:
    """Clamp a score into ``[0, 1]`` (defensive)."""
    return max(0.0, min(1.0, float(x)))


# --------------------------------------------------------------------------- #
# Availability probes (no heavy imports)                                      #
# --------------------------------------------------------------------------- #
def transformers_available() -> bool:
    """True if ``transformers`` *and* ``torch`` can be imported (no import)."""
    return (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
    )


def mat_entity_available() -> bool:
    """True if the vendored MatEntityRecognition package is importable."""
    for name in ("materials_entity_recognition", "MatEntityRecognition"):
        if importlib.util.find_spec(name) is not None:
            return True
    return False


@contextlib.contextmanager
def _otel_span(name: str, **attrs: object) -> Iterator[object]:
    """Best-effort OTel span; a no-op when OpenTelemetry is absent (§1.12)."""
    try:  # optional dependency — telemetry must never break extraction
        from opentelemetry import trace

        tracer = trace.get_tracer("kg_extractors.materials_ner")
        with tracer.start_as_current_span(name) as span:
            for key, value in attrs.items():
                with contextlib.suppress(Exception):
                    span.set_attribute(key, value)  # type: ignore[arg-type]
            yield span
    except Exception:
        yield None


# --------------------------------------------------------------------------- #
# MatSciBERT embeddings                                                        #
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=2)
def _load_matscibert(model_name: str, device: str):  # type: ignore[no-untyped-def]
    """Load MatSciBERT (tokenizer + model) once per ``(model, device)``."""
    import torch  # deferred optional import (§6.8)
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    if device and device != "cpu":
        with contextlib.suppress(Exception):  # GPU optional; degrade to CPU
            model = model.to(device)
    _log.info("matscibert.loaded", model=model_name, device=device)
    return tok, model, torch


def _hash_embed(text: str, dim: int = MATSCIBERT_HIDDEN) -> list[float]:
    """Deterministic L2-normalised fallback vector (offline; same ``dim``).

    Not semantically meaningful — it exists so the *shape* contract holds and the
    pipeline stays offline-safe. The backend name makes clear this is a fallback.
    """
    vec = [0.0] * dim
    tokens = re.findall(r"\w+", text.lower())
    for tokn in tokens:
        h = hashlib.blake2b(tokn.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


@dataclass(frozen=True, slots=True)
class EmbedReport:
    """Result of a batched MatSciBERT embedding pass (§6.8)."""

    backend: str  # "matscibert" | "hash-fallback"
    model: str | None
    dim: int
    n_texts: int
    latency_ms: float
    vectors: list[list[float]]

    def as_dict(self, *, include_vectors: bool = False) -> dict[str, object]:
        out: dict[str, object] = {
            "backend": self.backend,
            "model": self.model,
            "dim": self.dim,
            "n_texts": self.n_texts,
            "latency_ms": self.latency_ms,
        }
        if include_vectors:
            out["vectors"] = self.vectors
        return out


class MatSciBertEmbedder:
    """Batched MatSciBERT sentence embedder with an offline hashing fallback.

    ``embed_batch`` returns one mean-pooled, L2-normalised vector of
    :data:`MATSCIBERT_HIDDEN` dimensions per input text — a reusable embedding
    contract for indexing and entity resolution (§6.8).
    """

    def __init__(
        self, model_name: str = DEFAULT_MATSCIBERT, device: str = DEFAULT_DEVICE
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._real: bool | None = None  # resolved lazily on first embed

    @property
    def backend(self) -> str:
        if self._real is None:
            return "matscibert" if transformers_available() else "hash-fallback"
        return "matscibert" if self._real else "hash-fallback"

    def _embed_real(self, texts: Sequence[str]) -> list[list[float]]:
        tok, model, torch = _load_matscibert(self.model_name, self.device)
        with torch.no_grad():
            enc = tok(
                list(texts),
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            if self.device and self.device != "cpu":
                with contextlib.suppress(Exception):
                    enc = {k: v.to(self.device) for k, v in enc.items()}
            out = model(**enc)
            hidden = out.last_hidden_state  # (B, T, H)
            mask = enc["attention_mask"].unsqueeze(-1).type_as(hidden)  # (B, T, 1)
            summed = (hidden * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            pooled = summed / counts  # mean pooling over real tokens
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            return pooled.cpu().tolist()

    def embed_batch(self, texts: Sequence[str]) -> EmbedReport:
        """Embed a batch of texts; returns vectors of ``MATSCIBERT_HIDDEN`` dims."""
        started = time.perf_counter()
        items = [t or "" for t in texts]
        vectors: list[list[float]]
        with _otel_span("matscibert.embed_batch", **{"emb.n_texts": len(items)}):
            if transformers_available():
                try:
                    vectors = self._embed_real(items)
                    self._real = True
                except Exception as exc:  # no weights / offline / OOM → honest fallback
                    _log.warning(
                        "matscibert.embed_failed",
                        model=self.model_name,
                        error=str(exc)[:300],
                    )
                    self._real = False
                    vectors = [_hash_embed(t) for t in items]
            else:
                self._real = False
                vectors = [_hash_embed(t) for t in items]
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        dim = len(vectors[0]) if vectors else MATSCIBERT_HIDDEN
        report = EmbedReport(
            backend="matscibert" if self._real else "hash-fallback",
            model=self.model_name if self._real else None,
            dim=dim,
            n_texts=len(items),
            latency_ms=latency_ms,
            vectors=vectors,
        )
        _log.info(
            "matscibert.embed_batch",
            backend=report.backend,
            n_texts=report.n_texts,
            dim=report.dim,
            latency_ms=latency_ms,
        )
        return report


@functools.lru_cache(maxsize=2)
def get_embedder(
    model_name: str = DEFAULT_MATSCIBERT, device: str = DEFAULT_DEVICE
) -> MatSciBertEmbedder:
    """Process-cached :class:`MatSciBertEmbedder` (weights load at most once)."""
    return MatSciBertEmbedder(model_name, device)


# --------------------------------------------------------------------------- #
# MatEntityRecognition wrapper (+ deterministic materials-lexicon fallback)    #
# --------------------------------------------------------------------------- #
# Materials lexicon for the offline fallback. Tuned for the Russian mining /
# metallurgy corpus; every pattern anchors a real char span in the source text.
_ELEMENTS_RU = (
    "никель",
    "медь",
    "железо",
    "кобальт",
    "хром",
    "марганец",
    "титан",
    "алюминий",
    "цинк",
    "молибден",
    "вольфрам",
    "ванадий",
    "кремний",
    "углерод",
    "сера",
    "кислород",
    "водород",
)
_PROCESS_RU = (
    "электроэкстракц",
    "электролиз",
    "электроосажден",
    "выщелачивани",
    "флотаци",
    "обжиг",
    "спекани",
    "закалк",
    "отжиг",
    "отпуск",
    "цементаци",
    "азотировани",
    "легировани",
    "прокатк",
    "экстракц",
    "восстановлени",
    "окислени",
    "рафинировани",
)
_PROPERTY_RU = (
    "твёрдост",
    "твердост",
    "предел прочности",
    "прочност",
    "пластичност",
    "вязкост",
    "плотность тока",
    "плотност",
    "коррозионн",
    "износостойкост",
    "проводимост",
    "потенциал",
)
_METHOD_RU = (
    "дифрактометр",
    "рентгеноструктурн",
    "микроскоп",
    "спектроскоп",
    "хроматограф",
    "калориметр",
    "потенциостат",
)
# Chemical formula, e.g. Al2O3, NiSO4, TiO2; alloy grade, e.g. ХН77ТЮР, 12Х18Н10Т.
_RE_FORMULA = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")
_RE_ALLOY_RU = re.compile(r"\b[А-ЯA-Z]{1,3}\d{1,3}[А-ЯA-Zа-яa-z0-9]*\b")


def _lexicon_spans(text: str) -> list[NerSpan]:
    """Deterministic materials-NER fallback: anchored spans from the lexicon."""
    lowered = text.lower()
    spans: list[NerSpan] = []
    seen: set[tuple[int, int]] = set()

    def _add(start: int, end: int, label: str, score: float) -> None:
        if start < 0 or end <= start or end > len(text):
            return
        if (start, end) in seen:
            return
        seen.add((start, end))
        spans.append(
            NerSpan(text=text[start:end], label=label, start=start, end=end, score=score)
        )

    def _scan(terms: Sequence[str], label: str, score: float) -> None:
        for term in terms:
            from_ = 0
            while True:
                pos = lowered.find(term, from_)
                if pos < 0:
                    break
                # Extend to a word boundary so the surface form is complete.
                end = pos + len(term)
                while end < len(text) and text[end].isalpha():
                    end += 1
                _add(pos, end, label, score)
                from_ = pos + len(term)

    _scan(_ELEMENTS_RU, "chemical_element", 0.82)
    _scan(_PROCESS_RU, "processing_operation", 0.8)
    _scan(_PROPERTY_RU, "property", 0.8)
    _scan(_METHOD_RU, "method", 0.78)
    for m in _RE_ALLOY_RU.finditer(text):
        _add(m.start(), m.end(), "alloy", 0.85)
    for m in _RE_FORMULA.finditer(text):
        _add(m.start(), m.end(), "material", 0.8)

    spans.sort(key=lambda s: (s.start, s.end))
    return spans


class MatEntityRecognizer:
    """Materials-science NER as an :class:`~kg_extractors.ml_ner.NerBackend`.

    Wraps CederGroupHub MatEntityRecognition when vendored; otherwise runs the
    deterministic :func:`_lexicon_spans` tagger. Either way, ``extract`` returns
    anchored :class:`NerSpan` objects mapped onto the §8.1 domain labels.
    """

    name = "mat-entity"

    def __init__(self, device: str = DEFAULT_DEVICE) -> None:
        self.device = device
        self._model = None
        self._real = False
        if mat_entity_available():
            with contextlib.suppress(Exception):
                self._model = self._load_vendor()
                self._real = self._model is not None

    @property
    def backend(self) -> str:
        return "mat-entity" if self._real else "lexicon-fallback"

    def _load_vendor(self):  # type: ignore[no-untyped-def]
        """Load the vendored MatEntityRecognition inference model (best-effort)."""
        try:
            from materials_entity_recognition import MatIdentification  # type: ignore
        except Exception:
            from MatEntityRecognition import MatIdentification  # type: ignore
        return MatIdentification()

    def _extract_vendor(self, text: str) -> list[NerSpan]:
        """Run the vendored model and map its tagged tokens onto NerSpans."""
        # MatIdentification.mat_identify returns per-sentence token/tag lists.
        result = self._model.mat_identify(text)  # type: ignore[union-attr]
        spans: list[NerSpan] = []
        cursor = 0
        for sent in result:
            tokens = sent.get("tokens") if isinstance(sent, dict) else sent
            for tokobj in tokens or []:
                surface = str(tokobj.get("text", "")) if isinstance(tokobj, dict) else str(tokobj)
                tag = str(tokobj.get("tag", "MAT")) if isinstance(tokobj, dict) else "MAT"
                base = tag.split("-")[-1].upper()
                if base in ("O", ""):
                    continue
                if not surface:
                    continue
                pos = text.find(surface, cursor)
                if pos < 0:
                    pos = text.find(surface)
                if pos < 0:
                    continue
                end = pos + len(surface)
                cursor = end
                spans.append(
                    NerSpan(
                        text=text[pos:end],
                        label=MAT_TAG_MAP.get(base, "material"),
                        start=pos,
                        end=end,
                        score=0.9,
                    )
                )
        spans.sort(key=lambda s: (s.start, s.end))
        return spans

    def extract(self, text: str) -> list[NerSpan]:
        """Return anchored materials-NER spans (empty list for empty input)."""
        if not text or not text.strip():
            return []
        if self._real and self._model is not None:
            try:
                return self._extract_vendor(text)
            except Exception as exc:  # runtime failure → deterministic fallback
                _log.warning("mat_entity.extract_failed", error=str(exc)[:300])
        return _lexicon_spans(text)


@functools.lru_cache(maxsize=2)
def get_mat_recognizer(device: str = DEFAULT_DEVICE) -> MatEntityRecognizer:
    """Process-cached :class:`MatEntityRecognizer`."""
    return MatEntityRecognizer(device)


# --------------------------------------------------------------------------- #
# GLiNER ⊕ MatEntityRecognition fusion                                         #
# --------------------------------------------------------------------------- #
def _overlap(a: NerSpan, b: NerSpan) -> float:
    """Intersection-over-union of two char spans in ``[0, 1]``."""
    lo = max(a.start, b.start)
    hi = min(a.end, b.end)
    inter = max(0, hi - lo)
    if inter == 0:
        return 0.0
    union = (a.end - a.start) + (b.end - b.start) - inter
    return inter / union if union > 0 else 0.0


@dataclass(slots=True)
class FusedMention:
    """A fused mention with provenance across the two extractors (§6.8)."""

    text: str
    label: str
    char_start: int
    char_end: int
    score: float
    sources: list[str]  # e.g. ["gliner", "mat-entity"] — agreement is visible

    def as_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "label": self.label,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "score": round(self.score, 4),
            "sources": self.sources,
            "agreement": len(self.sources) > 1,
        }


def _combine_score(a: float, b: float) -> float:
    """Merge two confidences: agreement lifts the fused score (noisy-OR)."""
    return _clamp01(a + b - a * b)


def fuse_mentions(
    gliner_spans: Sequence[NerSpan],
    mat_spans: Sequence[NerSpan],
    *,
    iou_threshold: float = 0.5,
) -> list[FusedMention]:
    """Fuse GLiNER and MatEntityRecognition mentions, deduping on span overlap.

    Spans whose IoU ≥ ``iou_threshold`` are treated as the *same* mention: they
    are merged into one :class:`FusedMention` whose confidence is the noisy-OR of
    the inputs (so agreement raises it) and whose label is taken from the more
    confident span. A **full overlap therefore yields exactly one** mention — no
    duplicate — which is the §6.8 acceptance guarantee.
    """
    tagged = [("gliner", s) for s in gliner_spans] + [("mat-entity", s) for s in mat_spans]
    # Process most-confident first so the winning label is the strongest one.
    tagged.sort(key=lambda ts: ts[1].score, reverse=True)

    fused: list[FusedMention] = []
    for source, span in tagged:
        merged = False
        for fm in fused:
            probe = NerSpan(fm.text, fm.label, fm.char_start, fm.char_end, fm.score)
            if _overlap(probe, span) >= iou_threshold:
                if source not in fm.sources:
                    fm.sources.append(source)
                fm.score = _combine_score(fm.score, span.score)
                # Widen to the union of the two spans, keep the stronger label.
                if span.start < fm.char_start or span.end > fm.char_end:
                    lo, hi = min(fm.char_start, span.start), max(fm.char_end, span.end)
                    fm.char_start, fm.char_end = lo, hi
                merged = True
                break
        if not merged:
            fused.append(
                FusedMention(
                    text=span.text,
                    label=span.label,
                    char_start=span.start,
                    char_end=span.end,
                    score=span.score,
                    sources=[source],
                )
            )
    fused.sort(key=lambda fm: (fm.char_start, fm.char_end))
    return fused


@dataclass(frozen=True, slots=True)
class FusionReport:
    """Result of a fused NER pass over one text (§6.8)."""

    gliner_backend: str
    mat_backend: str
    n_gliner: int
    n_mat: int
    n_fused: int
    n_agreement: int
    latency_ms: float
    mentions: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        return {
            "gliner_backend": self.gliner_backend,
            "mat_backend": self.mat_backend,
            "n_gliner": self.n_gliner,
            "n_mat": self.n_mat,
            "n_fused": self.n_fused,
            "n_agreement": self.n_agreement,
            "latency_ms": self.latency_ms,
            "mentions": self.mentions,
        }


def _gliner_spans(text: str, *, threshold: float, device: str) -> tuple[str, list[NerSpan]]:
    """Run the §6.7 GLiNER extractor and return (backend_name, spans)."""
    from kg_extractors.gliner import DEFAULT_MODEL, DOMAIN_LABELS, get_backend

    backend = get_backend(DEFAULT_MODEL, threshold, DOMAIN_LABELS, device)
    spans = backend.extract(text or "")
    return getattr(backend, "name", "rule"), spans


def fuse_text(
    text: str,
    *,
    threshold: float = 0.5,
    iou_threshold: float = 0.5,
    device: str = DEFAULT_DEVICE,
) -> FusionReport:
    """Full §6.8 fusion for one passage: GLiNER ⊕ MatEntityRecognition."""
    started = time.perf_counter()
    with _otel_span("materials_ner.fuse_text", **{"ner.text_len": len(text or "")}):
        g_backend, g_spans = _gliner_spans(text, threshold=threshold, device=device)
        recognizer = get_mat_recognizer(device)
        m_spans = recognizer.extract(text or "")
        fused = fuse_mentions(g_spans, m_spans, iou_threshold=iou_threshold)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    n_agreement = sum(1 for fm in fused if len(fm.sources) > 1)
    report = FusionReport(
        gliner_backend=g_backend,
        mat_backend=recognizer.backend,
        n_gliner=len(g_spans),
        n_mat=len(m_spans),
        n_fused=len(fused),
        n_agreement=n_agreement,
        latency_ms=latency_ms,
        mentions=[fm.as_dict() for fm in fused],
    )
    _log.info(
        "materials_ner.fuse_text",
        gliner_backend=g_backend,
        mat_backend=recognizer.backend,
        n_gliner=len(g_spans),
        n_mat=len(m_spans),
        n_fused=len(fused),
        n_agreement=n_agreement,
        latency_ms=latency_ms,
    )
    return report
