"""Sparse fieldsets: ``?fields=`` projection of response bodies (§14.2).

Реализует разрежённые наборы полей (sparse fieldsets) из §14.2: клиент через
query-параметр ``?fields=`` перечисляет, какие ключи ответа оставить. Голые
токены — это включения (include), токены с префиксом ``-`` — исключения
(exclude); пробелы обрезаются. Чистый stdlib, без FastAPI.

Implements the ``?fields=`` sparse fieldset projection required by §14.2: the
client lists which response keys to keep. Bare tokens are includes, tokens
prefixed with ``-`` are excludes, and surrounding whitespace is stripped. Pure
standard library, no FastAPI:

* :class:`FieldMask`   — frozen (include, exclude) key-set carrier + ``as_dict``.
* :func:`parse_fields` — parse a comma-separated ``?fields=`` spec into a mask.
* :func:`project`      — apply a mask to a mapping, returning a plain ``dict``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Префикс токена-исключения / prefix that marks an exclude token in ``?fields=``.
_EXCLUDE_PREFIX = "-"
# Разделитель токенов в spec / token separator inside the ``?fields=`` value.
_SEP = ","


@dataclass(frozen=True)
class FieldMask:
    """Неизменяемая маска полей: include/exclude наборы ключей (§14.2).

    Frozen carrier for one field projection: ``include`` is the set of keys to
    keep (when non-empty it wins over ``exclude``), and ``exclude`` is the set
    of keys to drop when ``include`` is empty. Both are :class:`frozenset` so
    the mask is hashable and safe to share.
    """

    include: frozenset[str]
    exclude: frozenset[str]

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "include": sorted(self.include),
            "exclude": sorted(self.exclude),
        }


def parse_fields(spec: str | None) -> FieldMask:
    """Разобрать ``?fields=`` в :class:`FieldMask` (§14.2).

    Split the comma-separated ``spec`` into include/exclude key sets: a bare
    token becomes an include, a token prefixed with ``-`` becomes an exclude,
    and each token is whitespace-stripped. Empty tokens are ignored. A ``None``
    or blank ``spec`` yields an empty mask (both sets empty).
    """
    if spec is None:
        return FieldMask(include=frozenset(), exclude=frozenset())
    includes: set[str] = set()
    excludes: set[str] = set()
    for raw in spec.split(_SEP):
        token = raw.strip()
        if not token:
            continue
        if token.startswith(_EXCLUDE_PREFIX):
            key = token[len(_EXCLUDE_PREFIX) :].strip()
            if key:
                excludes.add(key)
        else:
            includes.add(token)
    return FieldMask(include=frozenset(includes), exclude=frozenset(excludes))


def project(obj: Mapping[str, object], mask: FieldMask) -> dict[str, object]:
    """Применить маску к отображению / apply ``mask`` to ``obj`` (§14.2).

    Return a plain ``dict`` projection of ``obj``: when ``mask.include`` is
    non-empty, keep only those keys that are present; otherwise drop every key
    listed in ``mask.exclude``. An empty mask (no includes, no excludes) yields
    an identity copy of ``obj``.
    """
    if mask.include:
        return {key: value for key, value in obj.items() if key in mask.include}
    if mask.exclude:
        return {key: value for key, value in obj.items() if key not in mask.exclude}
    return dict(obj)
