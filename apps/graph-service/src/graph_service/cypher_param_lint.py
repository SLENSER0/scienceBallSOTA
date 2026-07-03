"""Cypher template parameterization linter (§19.6).

Static check enforcing the §19.6 acceptance criterion that *every* Cypher
template is **fully parameterized** — only ``$params`` reach the graph, never a
user value spliced in by string interpolation / concatenation. Отдельный
линтер (linter), distinct from the sibling read-path guards:

- :mod:`graph_service.cypher_guard` — mutating-clause / ``LIMIT`` / allowlist;
- ``kg_retrievers.cypher_cost_guard`` — query cost.

This module never executes Cypher; it scans the *template source text* for the
tell-tale marks of value splicing:

- ``%s`` / ``%(name)s`` printf markers and ``{name}`` brace fields → ``string_interp``;
- an ``f"`` / ``f'`` f-string prefix → ``fstring``;
- a ``.format(`` call → ``format_call``;
- a quoted literal adjacent to ``+`` (``'a' + var``) → ``concat``;
- a single-quoted literal on the RHS of a ``WHERE ... =`` comparison
  (``WHERE n.name = 'Al'`` — a hard-coded / spliced filter value) → ``quoted_literal_filter``.

A clean template uses only ``$name`` placeholders; :func:`lint_template` also
collects those (sorted-unique) so callers can cross-check the bound param set.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# ``$name`` bound parameter — the *only* sanctioned way to pass a user value.
_PARAM = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

# printf-style ``%s`` / ``%(name)s`` and ``{name}`` brace interpolation fields.
_STRING_INTERP = re.compile(r"%\([A-Za-z_][A-Za-z0-9_]*\)s|%s|\{[A-Za-z_][A-Za-z0-9_]*\}")

# ``f"`` / ``f'`` (optionally ``rf`` / ``fr``) string prefix — not a bare word.
_FSTRING = re.compile(r"(?<![A-Za-z0-9_.])(?:[rR][fF]|[fF][rR]?)[\"']")

# ``.format(`` call.
_FORMAT_CALL = re.compile(r"\.format\s*\(")

# a quoted literal glued to ``+`` on either side — string concatenation.
_CONCAT = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1\s*\+|\+\s*['\"]")

# a single-quoted literal used as the RHS of a ``=`` filter comparison.
_QUOTED_LITERAL_FILTER = re.compile(r"=\s*'(?:\\.|[^'])*'")

# detector order is stable; findings are re-sorted by span for determinism.
_DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("string_interp", _STRING_INTERP),
    ("fstring", _FSTRING),
    ("format_call", _FORMAT_CALL),
    ("concat", _CONCAT),
    ("quoted_literal_filter", _QUOTED_LITERAL_FILTER),
)


@dataclass(frozen=True, slots=True)
class ParamLintFinding:
    """One parameterization violation (нарушение) in a Cypher template.

    ``kind`` ∈ ``{'string_interp','fstring','format_call','concat',
    'quoted_literal_filter'}``; ``span`` is the ``(start, end)`` char offset of
    the offending substring ``snippet`` within the template.
    """

    kind: str
    span: tuple[int, int]
    snippet: str

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view (для сериализации / for serialization)."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ParamLintReport:
    """Result of linting one Cypher template (отчёт / report).

    ``ok`` is ``True`` iff no findings — i.e. the template is fully
    parameterized. ``used_params`` are the sorted-unique ``$name`` placeholders.
    """

    template: str
    findings: tuple[ParamLintFinding, ...]
    used_params: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view; ``findings`` become a list of finding dicts."""
        return {
            "template": self.template,
            "findings": [f.as_dict() for f in self.findings],
            "used_params": list(self.used_params),
            "ok": self.ok,
        }


def _used_params(cypher: str) -> tuple[str, ...]:
    """Sorted, de-duplicated ``$name`` placeholders (плейсхолдеры)."""
    return tuple(sorted({m.group(1) for m in _PARAM.finditer(cypher)}))


def lint_template(cypher: str) -> ParamLintReport:
    """Lint one Cypher template for value-splicing anti-patterns (§19.6).

    Scans ``cypher`` with each detector, collects findings sorted by span, and
    gathers the sorted-unique ``$name`` params. ``ok`` is ``True`` iff clean.
    """
    findings: list[ParamLintFinding] = []
    for kind, pattern in _DETECTORS:
        for match in pattern.finditer(cypher):
            findings.append(ParamLintFinding(kind, match.span(), match.group(0)))
    findings.sort(key=lambda f: f.span)
    return ParamLintReport(
        template=cypher,
        findings=tuple(findings),
        used_params=_used_params(cypher),
        ok=not findings,
    )


def is_parameterized(cypher: str) -> bool:
    """``True`` iff ``cypher`` is fully parameterized (== ``lint_template(...).ok``)."""
    return lint_template(cypher).ok
