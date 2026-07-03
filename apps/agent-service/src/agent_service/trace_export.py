"""§13.23 экспорт трассировки с редактированием секретов / trace export with redaction.

Backs ``GET /internal/agent/trace/{session_id}`` (audit surface). ``tool_trace.py``
records raw entries, but an audit response must never leak credentials. This module
shapes those entries into an auditable, secret-redacted :class:`TraceExport`.

* :data:`DEFAULT_SENSITIVE` — key names whose values are secrets (пароли/токены).
* :func:`redact_args` — recursively replace sensitive values with ``'***'`` (case-
  insensitive on the key), preserving every other value and the nested structure.
* :func:`build_trace_export` — redact each entry's ``args``, count the calls and
  record which sensitive keys were actually redacted (какие ключи скрыты).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Значение-заглушка вместо секрета / placeholder written over any sensitive value.
_REDACTED = "***"

# Ключи-секреты по умолчанию (регистр не важен) / default secret key names (case-insensitive).
DEFAULT_SENSITIVE: frozenset[str] = frozenset(
    {"password", "token", "api_key", "authorization", "llm_api_key"}
)


@dataclass(frozen=True)
class TraceExport:
    """Auditable, redacted view of a session's tool trace (§13.23).

    Immutable snapshot returned by the internal trace endpoint: the ``session_id`` it
    belongs to, the redacted ``entries`` (tuple of dicts), how many ``tool_calls`` the
    trace held and the sorted ``redacted_keys`` that were scrubbed (какие ключи скрыты).
    """

    session_id: str
    entries: tuple[dict[str, Any], ...]
    tool_calls: int
    redacted_keys: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict (списки вместо кортежей / lists, not tuples)."""
        return {
            "session_id": self.session_id,
            "entries": [dict(entry) for entry in self.entries],
            "tool_calls": self.tool_calls,
            "redacted_keys": list(self.redacted_keys),
        }


def _is_sensitive(key: str, sensitive: frozenset[str]) -> bool:
    """True if ``key`` matches a sensitive name ignoring case (регистронезависимо)."""
    return key.lower() in sensitive


def redact_args(
    args: dict[str, Any], sensitive: frozenset[str] = DEFAULT_SENSITIVE
) -> dict[str, Any]:
    """Return a copy of ``args`` with every sensitive value replaced by ``'***'``.

    A key is sensitive when its lower-cased form is in ``sensitive`` (so ``API_KEY``
    and ``api_key`` both match). Matching is applied recursively through nested dicts
    and through dicts inside lists/tuples; non-sensitive scalars are copied unchanged
    (структура сохраняется / structure preserved). The input is never mutated.
    """
    redacted: dict[str, Any] = {}
    for key, value in args.items():
        if _is_sensitive(key, sensitive):
            redacted[key] = _REDACTED
        else:
            redacted[key] = _redact_value(value, sensitive)
    return redacted


def _redact_value(value: Any, sensitive: frozenset[str]) -> Any:
    """Recurse into nested containers, redacting sensitive keys within (вложенность)."""
    if isinstance(value, dict):
        return redact_args(value, sensitive)
    if isinstance(value, (list, tuple)):
        rebuilt = [_redact_value(item, sensitive) for item in value]
        return type(value)(rebuilt)
    return value


def _collect_redacted_keys(args: dict[str, Any], sensitive: frozenset[str]) -> set[str]:
    """Gather the sensitive keys actually present in ``args`` (recursively)."""
    found: set[str] = set()
    for key, value in args.items():
        if _is_sensitive(key, sensitive):
            found.add(key)
        elif isinstance(value, dict):
            found |= _collect_redacted_keys(value, sensitive)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, dict):
                    found |= _collect_redacted_keys(item, sensitive)
    return found


def build_trace_export(
    session_id: str,
    tool_trace: list[dict[str, Any]],
    sensitive: frozenset[str] = DEFAULT_SENSITIVE,
) -> TraceExport:
    """Build a redacted :class:`TraceExport` from a raw ``tool_trace`` list (§13.23).

    Each entry's ``'args'`` sub-dict is passed through :func:`redact_args`; entries are
    otherwise copied as-is. ``tool_calls`` is the number of entries and ``redacted_keys``
    is the sorted set of sensitive keys that were scrubbed across all entries (пусто,
    если секретов нет / empty tuple when nothing was sensitive). Input is not mutated.
    """
    entries: list[dict[str, Any]] = []
    redacted_keys: set[str] = set()
    for raw in tool_trace:
        entry = dict(raw)
        args = entry.get("args")
        if isinstance(args, dict):
            redacted_keys |= _collect_redacted_keys(args, sensitive)
            entry["args"] = redact_args(args, sensitive)
        entries.append(entry)
    return TraceExport(
        session_id=session_id,
        entries=tuple(entries),
        tool_calls=len(entries),
        redacted_keys=tuple(sorted(redacted_keys)),
    )
