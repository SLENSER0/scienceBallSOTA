"""ML-NER adapter with graceful rule fallback (§6.7).

GLiNER-style machine-learning NER is *optional*. When the ``gliner`` package is
installed, :func:`get_ner_backend` returns a GLiNER-backed adapter; otherwise it
falls back to :class:`RuleNerBackend`, which lifts spans out of the deterministic
rule extractor (§6). This keeps the pipeline OSS-only and dependency-light — the
ML model is a drop-in upgrade, never a hard requirement.

Design notes:
* Importing this module must **not** import ``gliner`` (it may be absent). The
  optional import is deferred to backend construction.
* Every :class:`NerSpan` is anchored to a real ``[start, end)`` offset in the
  source text. If an entity cannot be located, it is dropped rather than given a
  fabricated span — the "no source span → no fact" invariant (§3.3/§3.6).

Terminology (RU/EN): the corpus is Russian metallurgy, e.g. ``никель`` (nickel),
``электроэкстракция`` (electrowinning), ``католит`` (catholyte).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kg_extractors.rule_extractor import extract_rules

# Node type (taxonomy ``node_type`` / ``entity_type``) → coarse NER label.
# Unknown types fall through to an upper-cased form so labels are never empty.
_LABEL_MAP: dict[str, str] = {
    "Material": "MATERIAL",
    "Process": "PROCESS",
    "ProcessingRegime": "PROCESS",
    "TechnologySolution": "PROCESS",
    "Property": "PROPERTY",
    "Equipment": "EQUIPMENT",
    "Method": "METHOD",
    "Organization": "ORG",
}


def _to_label(entity_type: str) -> str:
    """Map an ``entity_type`` / taxonomy ``node_type`` to a NER label."""
    return _LABEL_MAP.get(entity_type, (entity_type or "ENTITY").upper())


def _clamp01(x: float) -> float:
    """Clamp a score into ``[0, 1]`` (defensive; schema already bounds it)."""
    return max(0.0, min(1.0, float(x)))


@dataclass(frozen=True, slots=True)
class NerSpan:
    """A named-entity span: surface ``text``, ``label`` and char offsets (§6.7).

    ``start``/``end`` are half-open indices into the source text, so
    ``text == source[start:end]`` by construction. ``score`` is in ``[0, 1]``.
    """

    text: str
    label: str
    start: int
    end: int
    score: float

    def as_dict(self) -> dict[str, object]:
        """Serialise to a plain dict (JSON-friendly)."""
        return {
            "text": self.text,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "score": self.score,
        }


@runtime_checkable
class NerBackend(Protocol):
    """Protocol for any NER backend: text in, ordered spans out."""

    def extract(self, text: str) -> list[NerSpan]:
        """Return NER spans found in ``text`` (empty list for empty input)."""
        ...


def _locate(source: str, lowered: str, ent) -> tuple[int, int] | None:  # type: ignore[no-untyped-def]
    """Resolve char offsets for an entity: explicit span, else literal find.

    Returns ``None`` when the surface form cannot be anchored in the text — such
    entities (e.g. declension-only loose matches) are dropped, not fabricated.
    """
    s, e = ent.span_start, ent.span_end
    if s is not None and e is not None and 0 <= s < e <= len(source):
        return s, e
    term = (ent.text or "").lower()
    if not term:
        return None
    pos = lowered.find(term)
    if pos < 0:
        return None
    return pos, pos + len(term)


class RuleNerBackend:
    """Fallback NER backend built on the deterministic rule extractor (§6).

    It re-runs :func:`~kg_extractors.rule_extractor.extract_rules`, maps each
    ``EntityExtract`` to a :class:`NerSpan`, using explicit spans when present and
    otherwise locating the surface form in the text.
    """

    name = "rule"

    def __init__(self, label_map: dict[str, str] | None = None) -> None:
        self._label_map = label_map or _LABEL_MAP

    def _label(self, entity_type: str) -> str:
        return self._label_map.get(entity_type, (entity_type or "ENTITY").upper())

    def extract(self, text: str) -> list[NerSpan]:
        if not text or not text.strip():
            return []
        doc = extract_rules(text)
        lowered = text.lower()
        spans: list[NerSpan] = []
        seen: set[tuple[int, int, str]] = set()
        for ent in doc.entities:
            off = _locate(text, lowered, ent)
            if off is None:
                continue
            start, end = off
            label = self._label(ent.entity_type)
            key = (start, end, label)
            if key in seen:
                continue
            seen.add(key)
            spans.append(
                NerSpan(
                    text=text[start:end],
                    label=label,
                    start=start,
                    end=end,
                    score=_clamp01(ent.confidence),
                )
            )
        spans.sort(key=lambda s: (s.start, s.end))
        return spans


class GlinerNerBackend:
    """GLiNER-backed NER adapter (§6.7), loaded lazily and only if available.

    Constructing this imports ``gliner``; callers should reach it through
    :func:`get_ner_backend`, which probes availability first. Kept import-safe so
    importing this module never requires the optional dependency.
    """

    name = "gliner"

    def __init__(
        self,
        model_name: str = "urchade/gliner_multi-v2.1",
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> None:
        from gliner import GLiNER  # deferred optional import (§6.7)

        self.labels = labels or ["material", "process", "property", "equipment"]
        self.threshold = threshold
        self._model = GLiNER.from_pretrained(model_name)

    def extract(self, text: str) -> list[NerSpan]:
        if not text or not text.strip():
            return []
        raw = self._model.predict_entities(text, self.labels, threshold=self.threshold)
        spans = [
            NerSpan(
                text=text[r["start"] : r["end"]],
                label=str(r.get("label", "")).upper() or "ENTITY",
                start=int(r["start"]),
                end=int(r["end"]),
                score=_clamp01(r.get("score", 1.0)),
            )
            for r in raw
        ]
        spans.sort(key=lambda s: (s.start, s.end))
        return spans


def _gliner_available() -> bool:
    """True if ``gliner`` can be imported — without importing it."""
    return importlib.util.find_spec("gliner") is not None


def get_ner_backend(name: str = "auto", **kwargs: object) -> NerBackend:
    """Return an NER backend by ``name`` (§6.7).

    * ``"auto"``  — GLiNER if importable, else the rule fallback.
    * ``"rule"``  — always the deterministic :class:`RuleNerBackend`.
    * ``"gliner"``— force GLiNER (raises ``ImportError`` if not installed).
    """
    key = (name or "auto").lower()
    if key == "rule":
        return RuleNerBackend()
    if key == "gliner":
        return GlinerNerBackend(**kwargs)  # type: ignore[arg-type]
    if key == "auto":
        if _gliner_available():
            return GlinerNerBackend(**kwargs)  # type: ignore[arg-type]
        return RuleNerBackend()
    raise ValueError(f"unknown NER backend: {name!r} (expected auto|rule|gliner)")
