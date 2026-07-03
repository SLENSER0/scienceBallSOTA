"""Cypher / query hardening + agent guardrails (§19.6).

Defense-in-depth for the read path. The agent never emits free Text2Cypher (it
calls structured, parameterized templates — ``KuzuGraphStore.rows(cypher,
params)``), but any query that *would* reach the graph on a read path is passed
through :func:`guard_read_query`, which:

- rejects mutating clauses (``CREATE/MERGE/DELETE/SET/REMOVE/DROP/LOAD CSV`` and
  write procedures ``apoc.*create*`` / ``dbms.*``) — keyword scan over the query
  with string/backtick literals stripped, so a keyword inside a quoted value is
  data, not a clause;
- enforces a ``LIMIT`` (default 1000) and an optional label/relationship
  allowlist.

Untrusted source content (document chunks, community summaries) that enters the
LLM context is treated as data, not instructions, via :func:`is_prompt_injection`
+ :func:`wrap_untrusted`.
"""

from __future__ import annotations

import re

DEFAULT_MAX_ROWS = 1000


class CypherGuardError(ValueError):
    """Raised when a query violates the read-path guard."""


_MUTATING = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|CREATE\s+INDEX)\b",
    re.IGNORECASE,
)
_WRITE_PROC = re.compile(
    r"\b(apoc\.(create|merge|refactor|periodic|trigger|export|load)"
    r"|dbms\.|db\.(create|index\.fulltext\.create))",
    re.IGNORECASE,
)
_LIMIT_TAIL = re.compile(r"\bLIMIT\s+\d+\s*;?\s*$", re.IGNORECASE)
_LABEL = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_REL = re.compile(r"\[[a-zA-Z0-9_]*:([A-Za-z_][A-Za-z0-9_]*)")


def _strip_literals(cypher: str) -> str:
    """Blank out single/double-quoted strings and backtick identifiers.

    So keywords that appear *inside a value* (``n.name = 'DELETE me'``) are not
    mistaken for clauses.
    """
    out = re.sub(r"'(?:\\.|[^'\\])*'", "''", cypher)
    out = re.sub(r'"(?:\\.|[^"\\])*"', '""', out)
    return re.sub(r"`(?:[^`])*`", "``", out)


def assert_read_only(cypher: str) -> None:
    scrubbed = _strip_literals(cypher)
    if _MUTATING.search(scrubbed):
        raise CypherGuardError("mutating clause rejected on read path")
    if _WRITE_PROC.search(scrubbed):
        raise CypherGuardError("write procedure rejected on read path")


def enforce_limit(cypher: str, max_rows: int = DEFAULT_MAX_ROWS) -> str:
    body = cypher.rstrip().rstrip(";").rstrip()
    if _LIMIT_TAIL.search(cypher.strip()):
        return body
    return f"{body}\nLIMIT {max_rows}"


def _check_allowlist(cypher: str, allowed: set[str] | None, pattern: re.Pattern, kind: str) -> None:
    if allowed is None:
        return
    used = set(pattern.findall(_strip_literals(cypher)))
    extra = used - allowed
    if extra:
        raise CypherGuardError(f"{kind} not in allowlist: {sorted(extra)}")


def guard_read_query(
    cypher: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    allowed_labels: set[str] | None = None,
    allowed_rels: set[str] | None = None,
) -> str:
    """Validate + harden a read-path Cypher query; raise CypherGuardError on violation."""
    assert_read_only(cypher)
    _check_allowlist(cypher, allowed_labels, _LABEL, "label")
    _check_allowlist(cypher, allowed_rels, _REL, "relationship")
    return enforce_limit(cypher, max_rows)


# -- prompt-injection guardrail --------------------------------------------
_INJECTION = re.compile(
    r"ignore\s+(all\s+|your\s+|the\s+)?previous\s+instructions"
    r"|disregard\s+(all\s+|the\s+)?(above|previous|prior)"
    r"|delete\s+the\s+graph|drop\s+(all|the|database)"
    r"|reveal\s+.*(secret|lab\s+[a-z]|restricted|password)"
    r"|you\s+are\s+now\s+|system\s*:\s*|new\s+instructions?\s*:",
    re.IGNORECASE,
)


def is_prompt_injection(text: str) -> bool:
    """Heuristic: does source text try to hijack the model or exfiltrate data?"""
    return bool(_INJECTION.search(text or ""))


def wrap_untrusted(text: str) -> str:
    """Fence source content so the LLM treats it as data, never as instructions."""
    return f"<untrusted_source_content>\n{text}\n</untrusted_source_content>"


def run_guarded(store, cypher, params=None, *, settings=None, **guard_kwargs):  # type: ignore[no-untyped-def]
    """Execute a read-path query through the guard, honoring ``ALLOW_RAW_CYPHER``.

    Raw Cypher is refused unless ``settings.allow_raw_cypher`` is set (default
    False); either way the query is validated + LIMIT-enforced before execution.
    Params must be passed separately (never string-concatenated) — Cypher
    injection defense.
    """
    if settings is None:
        from kg_common import get_settings

        settings = get_settings()
    if not settings.allow_raw_cypher:
        raise CypherGuardError("raw Cypher disabled — set ALLOW_RAW_CYPHER or use a template")
    hardened = guard_read_query(cypher, max_rows=settings.cypher_max_rows, **guard_kwargs)
    return store.rows(hardened, params or {})
