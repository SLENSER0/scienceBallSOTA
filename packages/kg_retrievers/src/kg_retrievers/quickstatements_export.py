"""Wikidata QuickStatements V1 export of KG facts (§22).

Serialises curated KG entities / statements into the Wikidata **QuickStatements**
V1 tab-separated syntax so a curator can push hand-vetted facts to Wikidata — a new
cross-KG interop (интероп) format alongside the RDF / GraphML / JSON-LD exporters.

QuickStatements V1 is line-oriented: each line is tab-joined ``subject predicate
value``. A bare ``CREATE`` mints a fresh item (referred to later on as ``LAST``);
labels use a ``L<lang>`` predicate with a **quoted** string value (значение в
кавычках); claims use a property id (``P31``) whose value is either a bare entity id
(``Q5``) or a quoted string literal.

Pure python (stdlib only): no graph/store access, no LLM, no clock. Deterministic —
line order follows input order. RU/EN.

Kuzu note: custom node props (label, aliases, claims, …) are *not* queryable columns —
a caller reading an entity from the store must ``RETURN`` base columns and hydrate the
rest via ``get_node`` before assembling the :class:`QsStatement` records handed here.

Entry points:

- :class:`QsStatement` — one QuickStatements line (subject / predicate / value);
- :func:`create_item` — the literal ``CREATE`` verb;
- :func:`label_statement` — a ``L<lang>`` label with a quoted string value;
- :func:`claim_statement` — a ``P<n>`` claim onto an entity or string target;
- :func:`to_qs` — render a sequence of statements as a QuickStatements document.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# QuickStatements V1 field separator — exactly one tab between the three columns.
_TAB = "\t"

# The bare verb that mints a fresh item (создать элемент); no subject/value columns.
_CREATE = "CREATE"


def _quote(text: str) -> str:
    """Wrap ``text`` in QuickStatements double quotes, escaping embedded quotes.

    A literal ``"`` inside a label/string value is escaped as ``\\"`` so the quoted
    span stays well-formed (кавычка экранируется). ``_quote('Al2O3') == '"Al2O3"'``.
    """
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class QsStatement:
    """One QuickStatements V1 line: ``subject`` / ``predicate`` / ``value`` (§22).

    ``value`` is stored **already rendered** — for labels and string literals it is the
    quoted form (``"Al2O3"``), for entity/property targets it is the bare id (``Q5``).
    ``is_label`` marks a ``L<lang>`` label row (in отличие от a claim), which callers /
    UIs use to group or style label edits separately from claims.
    """

    subject: str
    predicate: str
    value: str
    is_label: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict in stable field order (§22)."""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "is_label": self.is_label,
        }

    def as_line(self) -> str:
        """Render this statement as one tab-joined QuickStatements line (§22)."""
        return _TAB.join((self.subject, self.predicate, self.value))


def create_item() -> str:
    """Return the literal ``CREATE`` verb that mints a fresh Wikidata item (§22).

    ``create_item() == 'CREATE'``. In QuickStatements the newly created item is
    referred to as ``LAST`` by the lines that follow it.
    """
    return _CREATE


def label_statement(item: str, lang: str, text: str) -> QsStatement:
    """Build a label statement for ``item`` in ``lang`` (§22).

    Predicate is ``L<lang>`` (e.g. ``Len`` for English); the value is the **quoted**
    label text with embedded quotes escaped. ``is_label`` is ``True``.
    """
    return QsStatement(
        subject=item,
        predicate=f"L{lang}",
        value=_quote(text),
        is_label=True,
    )


def claim_statement(item: str, prop: str, target: str, *, is_string: bool = False) -> QsStatement:
    """Build a claim ``item prop target`` (§22).

    ``prop`` is a Wikidata property id (``P31``). When ``is_string`` is ``False``
    (default) ``target`` is treated as a bare entity/property id and left unquoted
    (``Q5``); when ``True`` it is a string literal and gets quoted (значение-строка).
    ``is_label`` is ``False``.
    """
    value = _quote(target) if is_string else target
    return QsStatement(subject=item, predicate=prop, value=value, is_label=False)


def to_qs(statements: Sequence[QsStatement]) -> str:
    """Render ``statements`` as a QuickStatements V1 document (§22).

    One tab-joined ``subject<TAB>predicate<TAB>value`` line per statement, joined by
    newlines in input order (порядок сохраняется). ``to_qs([]) == ''``. Values are
    emitted verbatim — labels/string literals already carry their quotes, entity
    targets stay bare.
    """
    return "\n".join(s.as_line() for s in statements)
