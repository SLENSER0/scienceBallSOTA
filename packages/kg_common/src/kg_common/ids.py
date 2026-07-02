"""Deterministic ID generation and canonical-key normalization (§3.8 / §9.7).

The same logical entity must always map to the same graph ID regardless of surface
form or mention order. IDs look like ``<prefix>:<slug-or-hash>``, e.g.
``material:al-cu-2024``, ``property:hardness``, ``exp:9f3c...``, ``ev:<uuid5>``.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid

# Stable namespace for uuid5-based IDs (Evidence, Measurement, ...).
_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

# Label -> id prefix (§3.4 LABEL_TO_ID_PREFIX). Kept in sync with kg_schema.labels.
LABEL_TO_ID_PREFIX: dict[str, str] = {
    "Document": "doc",
    "Paper": "paper",
    "Section": "sec",
    "Paragraph": "para",
    "Table": "table",
    "Figure": "fig",
    "Chunk": "chunk",
    "Evidence": "ev",
    "Claim": "claim",
    "Finding": "finding",
    "Experiment": "exp",
    "Sample": "sample",
    "Material": "material",
    "Alloy": "alloy",
    "ChemicalElement": "element",
    "Composition": "comp",
    "ProcessingRegime": "regime",
    "ProcessingStep": "step",
    "Parameter": "param",
    "Equipment": "equip",
    "Lab": "lab",
    "ResearchTeam": "team",
    "Person": "person",
    "Property": "property",
    "Measurement": "meas",
    "Unit": "unit",
    "Method": "method",
    "Dataset": "dataset",
    "Project": "project",
    "Decision": "decision",
    "CurationEvent": "curation",
    "Gap": "gap",
    "Contradiction": "contra",
    "ExtractorRun": "run",
    "GapScanRun": "gaprun",
    # domain (§24.2)
    "Geography": "geo",
    "Country": "country",
    "Facility": "facility",
    "TechnologySolution": "tech",
    "Recommendation": "rec",
    "TechnologyComparison": "cmp",
    "KnowledgeClaim": "kclaim",
    "Standard": "std",
    "Limitation": "limit",
    "ApplicabilityCondition": "appcond",
    "TechnoEconomicIndicator": "tei",
}

_WS = re.compile(r"[\s ]+")
_SEP = re.compile(r"[/\\.,;:()\[\]{}«»\"'`\-_]+")
_MULTIDASH = re.compile(r"-{2,}")
_NONSLUG = re.compile(r"[^a-z0-9а-яё\-]+")


def canonical_key(text: str) -> str:
    """Normalize a surface string to a canonical comparison key.

    Lowercase, Unicode NFKC, collapse whitespace/dashes. Used both for entity
    resolution keys and as the slug source for deterministic IDs. Cyrillic is
    preserved (RU/EN corpus).

    ``canonical_key("Al-Cu 2024") == canonical_key("al  cu   2024")``.
    """
    s = unicodedata.normalize("NFKC", text).strip().lower()
    s = _SEP.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def slugify(text: str, max_len: int = 64) -> str:
    """Human-readable slug for IDs (ascii+cyrillic, dashes)."""
    s = canonical_key(text).replace(" ", "-")
    s = _NONSLUG.sub("-", s)
    s = _MULTIDASH.sub("-", s).strip("-")
    return s[:max_len] or "x"


def short_hash(text: str, n: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def make_id(label: str, key: str, *, use_hash: bool = False) -> str:
    """Deterministic ``<prefix>:<slug|hash>`` id for a labelled entity.

    ``key`` is the canonical key (already or not normalized — we normalize again).
    Long/complex keys use a hash suffix for stability.
    """
    prefix = LABEL_TO_ID_PREFIX.get(label, label.lower())
    ck = canonical_key(key)
    if use_hash:
        return f"{prefix}:{short_hash(ck)}"
    slug = slugify(ck)
    # Keep slugs readable but avoid collisions on very long inputs.
    if len(slug) >= 60:
        return f"{prefix}:{slugify(ck, 40)}-{short_hash(ck, 8)}"
    return f"{prefix}:{slug}"


def uuid5_id(label: str, *parts: object) -> str:
    """Stable uuid5 id from parts (Evidence/Measurement — §3.8)."""
    prefix = LABEL_TO_ID_PREFIX.get(label, label.lower())
    joined = "|".join(str(p) for p in parts)
    return f"{prefix}:{uuid.uuid5(_NS, joined)}"


def regime_id(operation: str, temperature_c: object, time_h: object, atmosphere: object) -> str:
    """Deterministic id for a ProcessingRegime = hash(operation, T, t, atmosphere)."""
    atm = canonical_key(str(atmosphere or ""))
    key = f"{canonical_key(operation)}|{temperature_c}|{time_h}|{atm}"
    return make_id("ProcessingRegime", key, use_hash=True)


def evidence_id(doc_id: str, span: object, extractor_run_id: str) -> str:
    return uuid5_id("Evidence", doc_id, span, extractor_run_id)
