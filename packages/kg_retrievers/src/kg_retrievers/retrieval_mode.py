"""Retrieval-mode selection (§12.11 / §10.1 Mode A/B/C, routing §13.8).

RU: Выбор режима извлечения — структурный (Mode A), семантический (Mode B) или
глобальный (Mode C) — по интенту из таксономии §13.8 и эвристике над сырым
запросом. Чистая детерминированная логика без LLM: сначала интент (если он из
известной таксономии) задаёт режим, иначе включается эвристика по тексту запроса.
EN: Picks the retrieval mode — structured (Mode A / Cypher over exact
entities+params), semantic (Mode B / hybrid dense+sparse over chunks) or global
(Mode C / GraphRAG community summaries). Rule-first and deterministic (no LLM):
a known §13.8 intent decides the mode; otherwise a query-text heuristic does.

``strategies`` lists the retrieval channels to run for the chosen mode
(``graph`` / ``vector`` / ``keyword`` / ``community``) so the caller can fan out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Modes (§10.1 A/B/C) ------------------------------------------------------
MODE_STRUCTURED = "structured"  # Mode A — graph/Cypher over exact entities+params
MODE_SEMANTIC = "semantic"  # Mode B — hybrid dense/sparse over chunks
MODE_GLOBAL = "global"  # Mode C — GraphRAG community summaries (broad overview)

MODES: frozenset[str] = frozenset({MODE_STRUCTURED, MODE_SEMANTIC, MODE_GLOBAL})

# --- Retrieval channels (strategies) -----------------------------------------
CH_GRAPH = "graph"  # graph traversal / Cypher templates
CH_VECTOR = "vector"  # dense vector search
CH_KEYWORD = "keyword"  # sparse / BM25 keyword search
CH_COMMUNITY = "community"  # community-summary (GraphRAG) search

# Channels to run per mode. Each mode keeps a non-empty, deterministic channel set.
_MODE_STRATEGIES: dict[str, tuple[str, ...]] = {
    MODE_STRUCTURED: (CH_GRAPH, CH_VECTOR),
    MODE_SEMANTIC: (CH_VECTOR, CH_KEYWORD),
    MODE_GLOBAL: (CH_COMMUNITY, CH_VECTOR),
}

# --- Intent taxonomy (§13.8 Node 2, nine classes) → mode ---------------------
# Structured (Mode A / A+D): exact entities, numeric regimes, gaps, contradictions.
# Semantic  (Mode B): comparison, evidence lookup, schema help (hybrid chunk search).
# Global    (Mode C): broad literature summary over community summaries.
_INTENT_MODE: dict[str, str] = {
    "material_regime_property_query": MODE_STRUCTURED,
    "experiment_lookup": MODE_STRUCTURED,
    "entity_exploration": MODE_STRUCTURED,
    "gap_analysis": MODE_STRUCTURED,
    "contradiction_analysis": MODE_STRUCTURED,
    "method_comparison": MODE_SEMANTIC,
    "evidence_request": MODE_SEMANTIC,
    "schema_help": MODE_SEMANTIC,
    "literature_summary": MODE_GLOBAL,
}

# --- Query-text heuristic markers (RU + EN) ----------------------------------
_MATERIAL_MARKERS: tuple[str, ...] = (
    "alloy",
    "сплав",
    "steel",
    "сталь",
    "material",
    "материал",
    "composite",
    "композит",
    "polymer",
    "полимер",
    "ceramic",
    "керамик",
    "metal",
    "металл",
    "aluminum",
    "aluminium",
    "алюмин",
    "copper",
    "медь",
    "titanium",
    "титан",
)
_PROPERTY_MARKERS: tuple[str, ...] = (
    "hardness",
    "твердост",
    "strength",
    "прочност",
    "harden",
    "conductivity",
    "проводимост",
    "modulus",
    "модул",
    "toughness",
    "вязкост",
    "ductility",
    "пластичност",
    "yield",
    "текучест",
    "corrosion",
    "коррози",
    "property",
    "свойств",
)
_BROAD_MARKERS: tuple[str, ...] = (
    "overview",
    "обзор",
    "in general",
    "в целом",
    "what is known",
    "что известно",
    "directions",
    "направления",
    "landscape",
    "state of the art",
    "trend",
    "тенденци",
    "review",
    "summary of",
    "summarize",
    "big picture",
    "known about",
)
# A digit is a lightweight numeric-constraint marker (temperature / time / value).
_NUMERIC = re.compile(r"\d")

# Chemical-pair formulae such as "Al-Cu" also count as a material mention.
_FORMULA_PAIR = re.compile(r"\b[A-Z][a-z]?-[A-Z][a-z]?\b")


@dataclass(frozen=True)
class ModeDecision:
    """A resolved retrieval mode with its human-readable reason and channels (§12.11).

    ``mode`` is one of :data:`MODE_STRUCTURED` / :data:`MODE_SEMANTIC` /
    :data:`MODE_GLOBAL`; ``strategies`` are the channels to fan out over.
    """

    mode: str
    reason: str
    strategies: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "strategies": list(self.strategies),
        }


def strategies_for(mode: str) -> tuple[str, ...]:
    """Retrieval channels to run for ``mode`` (§12.11); raises on an unknown mode."""
    try:
        return _MODE_STRATEGIES[mode]
    except KeyError as exc:  # pragma: no cover - guard for programmer error
        raise ValueError(f"unknown retrieval mode: {mode!r}") from exc


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _heuristic(query: str) -> tuple[str, str]:
    """Pick a mode from the raw query text alone (§12.11); returns (mode, reason)."""
    has_broad = _has_any(query, _BROAD_MARKERS)
    has_material = _has_any(query, _MATERIAL_MARKERS) or bool(_FORMULA_PAIR.search(query))
    has_property = _has_any(query, _PROPERTY_MARKERS)
    has_numeric = bool(_NUMERIC.search(query))

    if has_broad:
        return MODE_GLOBAL, "broad/thematic query wording → global community search (Mode C)"
    if has_material and has_property and has_numeric:
        return (
            MODE_STRUCTURED,
            "material + property + numeric constraint → structured graph retrieval (Mode A)",
        )
    return MODE_SEMANTIC, "no structured/broad signal → semantic hybrid retrieval (Mode B)"


def select_mode(intent: str | None, query: str) -> ModeDecision:
    """Select the retrieval mode for ``intent`` (§13.8) + raw ``query`` (§12.11).

    A recognised §13.8 intent deterministically fixes the mode (intent overrides the
    query heuristic). An empty or unknown intent falls back to a text heuristic:
    structured for material+regime+property numeric asks, global for broad/thematic
    overviews, semantic otherwise. The result is always a valid, non-empty decision.
    """
    query_text = (query or "").lower()
    intent_key = (intent or "").strip().lower()

    if intent_key in _INTENT_MODE:
        mode = _INTENT_MODE[intent_key]
        reason = f"intent {intent_key!r} routed to {mode} retrieval (§13.8/§12.11)"
        return ModeDecision(mode=mode, reason=reason, strategies=_MODE_STRATEGIES[mode])

    mode, why = _heuristic(query_text)
    if intent_key:
        reason = f"unknown intent {intent_key!r}, fell back to query heuristic: {why}"
    else:
        reason = f"no intent given, query heuristic: {why}"
    return ModeDecision(mode=mode, reason=reason, strategies=_MODE_STRATEGIES[mode])
