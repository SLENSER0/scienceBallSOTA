"""Deterministic ID parsing & validation (§3.8) — inverse companion to ids.py.

``ids.py`` only *builds* deterministic IDs (``<prefix>:<slug|uuid5>``). Nothing
today parses one back to its label or checks that an id matches an expected label.
This module closes that gap: split an id into its parts, invert the
``LABEL_TO_ID_PREFIX`` map, and validate ids for a caller-supplied label.

Разбор и валидация детерминированных идентификаторов (§3.8): обратная сторона
``ids.py`` — из ``<prefix>:<slug|uuid5>`` восстановить префикс/метку и проверить.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from kg_common.ids import LABEL_TO_ID_PREFIX

# Prefix -> Label (inverse of LABEL_TO_ID_PREFIX). Prefixes are unique in the
# forward map, so the inverse is well-defined. / Обратное отображение префикс->метка.
_PREFIX_TO_LABEL: dict[str, str] = {prefix: label for label, prefix in LABEL_TO_ID_PREFIX.items()}


@dataclass(frozen=True)
class ParsedId:
    """A deterministic id split into its constituent parts (§3.8).

    ``raw`` — исходная строка; ``prefix`` — id-префикс (``material``, ``ev``, ...);
    ``key`` — часть после первого ``:``; ``is_uuid`` — является ли key uuid5-ключом.
    """

    raw: str
    prefix: str
    key: str
    is_uuid: bool

    def as_dict(self) -> dict[str, Any]:
        """Serializable view of the parsed id. / Словарь для сериализации."""
        return asdict(self)


def is_uuid5_key(key: str) -> bool:
    """True if ``key`` is a canonical UUID string (uuid5 id part — §3.8).

    Проверяем, что ключ — валидный UUID и его каноническая форма совпадает
    с исходной (отсекаем «почти-uuid» строки).
    """
    try:
        return str(uuid.UUID(key)) == key.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def parse_id(id_str: str) -> ParsedId:
    """Split a deterministic id on the first ``:`` into a :class:`ParsedId`.

    Разбиваем по первому двоеточию: часть слева — префикс, справа — ключ.
    Строка без двоеточия даёт пустой ``prefix`` и ``key == raw`` (невалидный id).
    """
    if ":" in id_str:
        prefix, key = id_str.split(":", 1)
    else:
        prefix, key = "", id_str
    return ParsedId(raw=id_str, prefix=prefix, key=key, is_uuid=is_uuid5_key(key))


def label_for_prefix(prefix: str) -> str | None:
    """Inverse of ``LABEL_TO_ID_PREFIX``: id-prefix -> Label, or ``None``.

    ``label_for_prefix("material") == "Material"``; неизвестный префикс -> ``None``.
    """
    return _PREFIX_TO_LABEL.get(prefix)


def validate_id(id_str: str, expected_label: str | None = None) -> bool:
    """Validate a deterministic id, optionally against an expected label (§3.8).

    An id is valid when it contains a ``:``, has a non-empty key, and its prefix
    maps back to a known label. When ``expected_label`` is given, that label must
    match the prefix's label. / Валиден при наличии ``:``, непустого ключа и
    известного префикса; при заданной метке она должна совпасть.
    """
    if ":" not in id_str:
        return False
    parsed = parse_id(id_str)
    if not parsed.key:
        return False
    label = label_for_prefix(parsed.prefix)
    if label is None:
        return False
    if expected_label is not None:
        return label == expected_label
    return True
