"""Download/export ``Content-Disposition`` + media-type building (§14.9).

Централизует сборку заголовков ``Content-Disposition``/``Content-Type`` для
выгрузок §14.8/§14.9/§14.15. Сейчас роутер экспериментов умеет только
``inline``; этот модуль на чистом stdlib даёт безопасное имя файла, выбор
media type по расширению и готовый словарь заголовков как для скачивания
(``attachment``), так и для просмотра в браузере (``inline``).

Centralises the ``Content-Disposition``/``Content-Type`` header building used by
the §14.8/§14.9/§14.15 downloads (only ``inline`` lives in the experiments
router today). Pure standard library:

* :class:`Disposition`      — frozen ``{filename, media_type, inline}`` carrier.
* :func:`safe_filename`     — basename + non-``[A-Za-z0-9._-]`` chars → ``_``.
* :func:`media_type_for`    — extension → MIME type (fallback octet-stream).
* :func:`content_disposition` — render the ``Content-Disposition`` header value.
* :func:`export_headers`    — ``{Content-Disposition, Content-Type}`` header dict.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Anything outside the safe set is collapsed to a single underscore per char.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# Расширение → media type / extension → MIME media type (§14.9).
_MEDIA_TYPES: dict[str, str] = {
    "csv": "text/csv",
    "json": "application/json",
    "md": "text/markdown",
    "pdf": "application/pdf",
    "png": "image/png",
}

_DEFAULT_MEDIA_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class Disposition:
    """Неизменяемое описание выгрузки для заголовков ответа (§14.9).

    Frozen carrier for one download: the (already sanitised) ``filename``, the
    resolved ``media_type`` and whether it is served ``inline`` (browser view)
    or as an ``attachment`` (save dialog). :meth:`header_value` renders the
    ``Content-Disposition`` value, :meth:`as_dict` gives a plain field view.
    """

    filename: str
    media_type: str
    inline: bool

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "filename": self.filename,
            "media_type": self.media_type,
            "inline": self.inline,
        }

    def header_value(self) -> str:
        """``Content-Disposition`` значение / the header value (§14.9)."""
        return content_disposition(self.filename, inline=self.inline)


def safe_filename(name: str) -> str:
    """Безопасное имя файла: basename + запрет небезопасных символов (§14.9).

    Takes the path basename (so ``../../etc/passwd`` cannot escape the export
    directory) and replaces every character outside ``[A-Za-z0-9._-]`` with an
    underscore, e.g. ``a b/c?.csv`` → ``c_.csv``.
    """
    base = os.path.basename(name)
    return _UNSAFE.sub("_", base)


def media_type_for(ext: str) -> str:
    """Media type по расширению; иначе octet-stream / MIME for ``ext`` (§14.9).

    The extension is matched case-insensitively with any leading dot stripped
    (``csv`` → ``text/csv``); an unknown extension falls back to
    ``application/octet-stream``.
    """
    key = ext.lower().lstrip(".")
    return _MEDIA_TYPES.get(key, _DEFAULT_MEDIA_TYPE)


def content_disposition(filename: str, inline: bool = False) -> str:
    """Собрать значение ``Content-Disposition`` для ``filename`` (§14.9).

    Renders ``attachment; filename="<safe>"`` by default, or ``inline;
    filename="<safe>"`` when ``inline`` is set. The name is always passed
    through :func:`safe_filename` first so the quoted value is never a path.
    """
    disposition = "inline" if inline else "attachment"
    return f'{disposition}; filename="{safe_filename(filename)}"'


def export_headers(
    filename: str,
    media_type: str | None = None,
    inline: bool = False,
) -> dict[str, str]:
    """Заголовки выгрузки ``Content-Disposition`` + ``Content-Type`` (§14.9).

    Returns exactly ``{"Content-Disposition", "Content-Type"}``. When
    ``media_type`` is ``None`` it is inferred from the filename extension via
    :func:`media_type_for`; ``inline`` selects browser view vs. save dialog.
    """
    if media_type is None:
        _, _, ext = filename.rpartition(".")
        media_type = media_type_for(ext)
    return {
        "Content-Disposition": content_disposition(filename, inline=inline),
        "Content-Type": media_type,
    }
