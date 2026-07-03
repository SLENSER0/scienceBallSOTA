"""Typed asset metadata values — типизированные метаданные ассетов (§9.8).

Section 9.8 attaches structured metadata to a Dagster ``MaterializeResult`` so
that counts, S3 links and run ids surface in the asset catalog. This module
mirrors Dagster's ``MetadataValue`` with a *pure*, JSON-serialisable builder —
«чистый и сериализуемый» — that can be unit-tested without importing Dagster.

A :class:`MetadataValue` is a frozen ``(kind, value)`` pair whose
:meth:`MetadataValue.as_dict` emits ``{'type': kind, 'value': value}``. The
``kind`` is one of ``int | float | text | url | path | json``. Typed
constructors (:func:`md_int`, :func:`md_float`, :func:`md_text`, :func:`md_url`,
:func:`md_path`, :func:`md_json`) validate/coerce their input and raise
``TypeError`` on mismatch.

:func:`build_asset_metadata` assembles an *ordered* ``name -> as_dict()`` mapping
from asset counts, optional S3 URIs and optional run/schema identifiers, skipping
any optional that was not supplied — «пропускаем необязательные поля».

Public API:

* :class:`MetadataValue` — frozen typed metadata pair with :meth:`as_dict`.
* :func:`md_int` / :func:`md_float` / :func:`md_text` — scalar constructors.
* :func:`md_url` / :func:`md_path` — location constructors.
* :func:`md_json` — structured-value constructor.
* :func:`build_asset_metadata` — ordered metadata mapping for an asset output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "MetadataValue",
    "build_asset_metadata",
    "md_float",
    "md_int",
    "md_json",
    "md_path",
    "md_text",
    "md_url",
]

# Allowed metadata kinds — допустимые виды метаданных (§9.8).
_KINDS: frozenset[str] = frozenset({"int", "float", "text", "url", "path", "json"})

# JSON-serialisable leaf/container types — сериализуемые типы (§9.8).
_JSON_TYPES: tuple[type, ...] = (dict, list, str, int, float, bool, type(None))


@dataclass(frozen=True)
class MetadataValue:
    """A frozen typed metadata pair — типизированная пара метаданных (§9.8).

    ``kind`` selects the metadata renderer (mirroring Dagster ``MetadataValue``)
    and ``value`` holds the already-coerced payload. Construct via the ``md_*``
    helpers rather than directly so the value is validated for its ``kind``.
    """

    kind: str
    value: object

    def __post_init__(self) -> None:
        """Reject unknown kinds — отвергаем неизвестные виды (§9.8)."""
        if self.kind not in _KINDS:
            raise ValueError(f"unknown metadata kind: {self.kind!r}")

    def as_dict(self) -> dict[str, object]:
        """Emit the Dagster-shaped dict — представление словарём (§9.8)."""
        return {"type": self.kind, "value": self.value}


def md_int(v: object) -> MetadataValue:
    """Build an ``int`` metadata value — целочисленная метадата (§9.8).

    Rejects ``bool`` and ``float`` to avoid silent ``1.5 -> 1`` truncation —
    «без тихого усечения».
    """
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError(f"md_int expects int, got {type(v).__name__}")
    return MetadataValue("int", v)


def md_float(v: object) -> MetadataValue:
    """Build a ``float`` metadata value — вещественная метадата (§9.8).

    Accepts ``int`` (coerced to ``float``) but rejects ``bool``.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError(f"md_float expects float, got {type(v).__name__}")
    return MetadataValue("float", float(v))


def md_text(v: object) -> MetadataValue:
    """Build a free-text metadata value — текстовая метадата (§9.8)."""
    if not isinstance(v, str):
        raise TypeError(f"md_text expects str, got {type(v).__name__}")
    return MetadataValue("text", v)


def md_url(v: object) -> MetadataValue:
    """Build a URL metadata value — ссылка-URL (§9.8)."""
    if not isinstance(v, str):
        raise TypeError(f"md_url expects str, got {type(v).__name__}")
    return MetadataValue("url", v)


def md_path(v: object) -> MetadataValue:
    """Build a filesystem/URI path metadata value — путь (§9.8)."""
    if not isinstance(v, str):
        raise TypeError(f"md_path expects str, got {type(v).__name__}")
    return MetadataValue("path", v)


def md_json(v: object) -> MetadataValue:
    """Build a structured JSON metadata value — структурная метадата (§9.8).

    Accepts only JSON-serialisable containers/leaves — «только JSON-типы».
    """
    if isinstance(v, bool) or not isinstance(v, _JSON_TYPES):
        raise TypeError(f"md_json expects a JSON value, got {type(v).__name__}")
    return MetadataValue("json", v)


def build_asset_metadata(
    *,
    counts: Mapping[str, int],
    s3_uris: Sequence[str] = (),
    extraction_run_id: str | None = None,
    schema_version: str | None = None,
) -> dict[str, dict]:
    """Assemble ordered asset metadata — упорядоченная метадата ассета (§9.8).

    Emits, in order: one ``int`` entry per name in ``counts``; a single ``path``
    entry ``s3_uris`` when at least one URI is supplied; a ``text``
    ``extraction_run_id`` when given; a ``text`` ``schema_version`` when given.
    Omitted optionals contribute no keys — «пропущенное поле не даёт ключа».
    """
    out: dict[str, dict] = {}
    for name, count in counts.items():
        out[name] = md_int(count).as_dict()
    if len(s3_uris) > 0:
        out["s3_uris"] = md_path("\n".join(s3_uris)).as_dict()
    if extraction_run_id is not None:
        out["extraction_run_id"] = md_text(extraction_run_id).as_dict()
    if schema_version is not None:
        out["schema_version"] = md_text(schema_version).as_dict()
    return out
