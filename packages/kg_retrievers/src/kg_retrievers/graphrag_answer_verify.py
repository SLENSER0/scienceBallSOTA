"""GraphRAG answer verification / hallucination guard (§11.13).

A GraphRAG answer (ответ) is only trustworthy when every numeric claim it makes is
grounded in the retrieved source texts (тексты-источники) and every document it
cites (документ) was actually part of the retrieval context. This module performs a
deterministic, offline (no-LLM) check over a finished answer string:

- ``numeric_claims`` — numeric tokens (числовые утверждения) extracted from the
  answer, including ranges and units (e.g. ``"320 MPa"``, ``"12-28 %"``);
- ``unsupported_numbers`` — magnitudes whose value does not appear in *any*
  ``source_text`` (флаг галлюцинации);
- ``unknown_citations`` — document ids referenced by the answer that were not part
  of the cited retrieval context (неизвестная цитата).

The answer is ``ok`` only when both the unsupported and unknown lists are empty.
Complements the citation tracing in :mod:`kg_retrievers.graphrag_citations` (§11.11).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from kg_common import get_logger

_log = get_logger("graphrag_answer_verify")

# Numeric token: an optional leading number, an optional range tail (``-``/``–``/``to``),
# then an optional unit made of letters / ``%`` / ``°`` (e.g. "MPa", "%", "HV", "°C").
_NUM_TOKEN = re.compile(
    r"""
    (?<![\w.])                       # not preceded by word char / decimal point
    (\d+(?:[.,]\d+)?)                # first magnitude (int or decimal)
    (?:\s*(?:-|–|—|to)\s*            # optional range separator
       (\d+(?:[.,]\d+)?))?           # second magnitude of the range
    (?:\s*(%|°[CF]?|[A-Za-z][A-Za-z/·]*))?   # optional unit
    """,
    re.VERBOSE,
)

# A bare magnitude, used to test grounding of each number against source text.
_MAGNITUDE = re.compile(r"\d+(?:[.,]\d+)?")


def _magnitudes(text: str) -> set[str]:
    """Return the set of bare numeric magnitudes appearing anywhere in ``text``."""
    return {m.group(0).replace(",", ".") for m in _MAGNITUDE.finditer(text)}


def extract_numbers(text: str) -> list[str]:
    """Extract numeric tokens (with ranges/units) from ``text``, in order (§11.13).

    Each token keeps its magnitude(s) and trailing unit, e.g. ``"320 MPa"`` or
    ``"12-28 %"``. Whitespace inside a token is normalised to single spaces.
    Duplicate tokens are preserved (a claim may legitimately repeat).
    """
    out: list[str] = []
    for m in _NUM_TOKEN.finditer(text):
        token = " ".join(m.group(0).split())
        if token:
            out.append(token)
    return out


@dataclass(frozen=True)
class AnswerCheck:
    """Result of verifying a GraphRAG answer against its sources (§11.13).

    Attributes:
        ok: ``True`` only when no unsupported number and no unknown citation remain.
        numeric_claims: numeric tokens extracted from the answer, in order.
        unsupported_numbers: magnitudes not found in any source text (галлюцинации).
        unknown_citations: cited doc ids absent from the retrieval context.
    """

    ok: bool
    numeric_claims: tuple[str, ...]
    unsupported_numbers: tuple[str, ...]
    unknown_citations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (copies the tuples to lists)."""
        return {
            "ok": self.ok,
            "numeric_claims": list(self.numeric_claims),
            "unsupported_numbers": list(self.unsupported_numbers),
            "unknown_citations": list(self.unknown_citations),
        }


def verify_answer(
    answer: str,
    *,
    source_texts: list[str],
    cited_doc_ids: list[str],
    answer_doc_ids: list[str],
) -> AnswerCheck:
    """Verify an answer's numbers and citations against the retrieval context (§11.13).

    Every numeric token in ``answer`` is extracted; a token's magnitude is
    *unsupported* when it does not appear in any of ``source_texts``. Every id in
    ``answer_doc_ids`` that is not present in ``cited_doc_ids`` is an *unknown*
    citation. The answer is ``ok`` only when both lists are empty. Deterministic
    and offline-safe (no LLM).
    """
    claims = extract_numbers(answer)

    supported: set[str] = set()
    for src in source_texts:
        supported |= _magnitudes(src)

    unsupported: list[str] = []
    seen_unsupported: set[str] = set()
    for token in claims:
        mags = [m.group(0).replace(",", ".") for m in _MAGNITUDE.finditer(token)]
        for mag in mags:
            if mag not in supported and mag not in seen_unsupported:
                seen_unsupported.add(mag)
                unsupported.append(mag)

    cited = set(cited_doc_ids)
    unknown: list[str] = []
    seen_unknown: set[str] = set()
    for did in answer_doc_ids:
        if did and did not in cited and did not in seen_unknown:
            seen_unknown.add(did)
            unknown.append(did)

    ok = not unsupported and not unknown
    if not ok:
        _log.debug("answer verify failed: unsupported=%s unknown=%s", unsupported, unknown)
    return AnswerCheck(
        ok=ok,
        numeric_claims=tuple(claims),
        unsupported_numbers=tuple(unsupported),
        unknown_citations=tuple(unknown),
    )


def _roundtrip(check: AnswerCheck) -> str:
    """Return the JSON encoding of ``check`` (helper for callers/tests)."""
    return json.dumps(check.as_dict(), ensure_ascii=False, sort_keys=True)
