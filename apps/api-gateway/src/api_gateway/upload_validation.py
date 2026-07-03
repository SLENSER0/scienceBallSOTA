"""Pre-flight MIME/size validation for ``POST /documents/upload`` (§14.9).

Проверяет загружаемые документы ещё до чтения тела запроса: разрешённый
MIME-тип (allowlist по расширению) и лимит размера 200 МБ. При нарушении
роутер отдаёт ``413`` (слишком большой файл) либо ``415`` (неподдерживаемый
тип). Модуль на чистом stdlib — валидация выгрузок живёт в
``content_disposition.py``, отдельного модуля проверки загрузок не было.

Pre-flight validation for uploaded documents, run before the request body is
read: an allowed MIME type (extension allowlist) and a 200 MB size ceiling.
The router turns a failure into ``413`` (too large) or ``415`` (unsupported
type). Pure standard library — ``content_disposition.py`` only builds download
headers, so upload validation had no home before.

* :data:`ALLOWED_UPLOAD_TYPES` — ext → MIME allowlist (pdf/docx/txt/csv/md/html).
* :data:`MAX_UPLOAD_BYTES`      — 200 MB hard size ceiling.
* :class:`UploadCheck`          — frozen ``{ok, media_type, size, reason}``.
* :func:`sniff_media_type`      — case-insensitive extension → MIME.
* :func:`is_allowed`            — is a ``content_type`` in the allowlist.
* :func:`validate_upload`       — full pre-flight check → :class:`UploadCheck`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Расширение → MIME media type (allowlist) / extension → MIME (§14.9).
ALLOWED_UPLOAD_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "csv": "text/csv",
    "md": "text/markdown",
    "html": "text/html",
}

# Жёсткий лимит размера тела: 200 МБ / hard body-size ceiling: 200 MB (§14.9).
MAX_UPLOAD_BYTES: int = 200 * 1024 * 1024

# Множество разрешённых MIME-типов / set of allowed MIME types.
_ALLOWED_MIME: frozenset[str] = frozenset(ALLOWED_UPLOAD_TYPES.values())


@dataclass(frozen=True)
class UploadCheck:
    """Неизменяемый результат проверки загрузки (§14.9).

    Frozen carrier for one pre-flight decision: whether the upload is ``ok``,
    the resolved ``media_type`` (sniffed from the filename, ``None`` on an
    unknown extension), the reported ``size`` in bytes, and a machine ``reason``
    for a rejection (``empty`` / ``unsupported_type`` / ``too_large``) or
    ``None`` when accepted.
    """

    ok: bool
    media_type: str | None
    size: int
    reason: str | None

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "ok": self.ok,
            "media_type": self.media_type,
            "size": self.size,
            "reason": self.reason,
        }


def sniff_media_type(filename: str) -> str | None:
    """MIME по расширению файла (регистронезависимо) / MIME for ``filename`` (§14.9).

    Takes the path basename, lowercases the extension and looks it up in
    :data:`ALLOWED_UPLOAD_TYPES`; returns ``None`` for an unknown or missing
    extension, e.g. ``sniff_media_type("X.PDF") == "application/pdf"``.
    """
    base = os.path.basename(filename)
    _, dot, ext = base.rpartition(".")
    if not dot:
        return None
    return ALLOWED_UPLOAD_TYPES.get(ext.lower())


def is_allowed(content_type: str) -> bool:
    """Входит ли MIME в allowlist / is ``content_type`` allowed (§14.9)."""
    return content_type in _ALLOWED_MIME


def validate_upload(
    filename: str,
    content_type: str,
    size: int,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> UploadCheck:
    """Полная pre-flight проверка загрузки / full upload pre-flight (§14.9).

    Rejects, in order: an empty body (``reason="empty"``), a type that is not in
    the allowlist by either the declared ``content_type`` or the filename
    extension (``reason="unsupported_type"``), and a body over ``max_bytes``
    (``reason="too_large"``). On success ``ok`` is ``True`` and ``media_type``
    is the sniffed MIME (falling back to the declared ``content_type``).
    """
    sniffed = sniff_media_type(filename)
    media_type = sniffed if sniffed is not None else (content_type or None)

    if size <= 0:
        return UploadCheck(ok=False, media_type=media_type, size=size, reason="empty")

    if sniffed is None or not is_allowed(content_type):
        return UploadCheck(ok=False, media_type=media_type, size=size, reason="unsupported_type")

    if size > max_bytes:
        return UploadCheck(ok=False, media_type=media_type, size=size, reason="too_large")

    return UploadCheck(ok=True, media_type=media_type, size=size, reason=None)
