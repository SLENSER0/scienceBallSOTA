"""Upload validation guard — проверка загрузок (§19.4).

To resist abuse via malicious uploads we validate every inbound file against a
frozen :class:`UploadPolicy` *before* it is persisted or parsed. The checks are
cheap and ordered so the cheapest / most decisive failure wins: byte **size**
(«слишком большой файл» → HTTP 413), then the declared **content-type** against
an allowlist (→ 415), then a **magic-byte** prefix match so a declared type
cannot lie about the actual bytes («подмена типа» → 415). Filenames are
sanitised to their basename with path separators, ``..`` and control/NUL chars
stripped, defeating path-traversal. Pure-python, stdlib only.

Reasons: ``'too_large'`` | ``'content_type'`` | ``'magic_mismatch'`` | ``'ok'``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UploadPolicy:
    """Policy governing which uploads are permitted («политика загрузок»).

    :param max_bytes: maximum accepted payload size in bytes (inclusive).
    :param allowed_content_types: declared content-types that may be accepted.
    :param magic_signatures: content-type → required leading byte prefixes; any
        one matching prefix satisfies the magic check for that type.
    """

    max_bytes: int
    allowed_content_types: frozenset[str]
    magic_signatures: Mapping[str, tuple[bytes, ...]]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this policy («сериализация политики»)."""
        return {
            "max_bytes": self.max_bytes,
            "allowed_content_types": sorted(self.allowed_content_types),
            "magic_signatures": {
                ct: [sig.hex() for sig in sigs]
                for ct, sigs in sorted(self.magic_signatures.items())
            },
        }


@dataclass(frozen=True)
class UploadVerdict:
    """Outcome of validating one upload («вердикт по загрузке»).

    :param status: HTTP-style numeric status code (200 / 413 / 415).
    :param ok: ``True`` only when the upload passed every check.
    :param reason: machine-readable reason token (see module docstring).
    :param safe_filename: sanitised basename safe to persist.
    """

    status: int
    ok: bool
    reason: str
    safe_filename: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this verdict («сериализация вердикта»)."""
        return {
            "status": self.status,
            "ok": self.ok,
            "reason": self.reason,
            "safe_filename": self.safe_filename,
        }


def sanitize_filename(name: str) -> str:
    """Strip path separators, ``..`` and control/NUL chars, keeping the basename.

    «Возвращаем только имя файла без путей и управляющих символов» — defeats
    path-traversal (``../../etc/passwd`` → ``passwd``) and NUL-injection.
    """
    # Drop control characters (incl. NUL); normalise both separators to '/'.
    cleaned = "".join(ch for ch in name if ord(ch) >= 32).replace("\\", "/")
    # Keep only the final path segment, then neutralise any residual ``..``.
    base = os.path.basename(cleaned)
    if base in ("..", "."):
        base = ""
    return base.replace("..", "")


def validate_upload(
    policy: UploadPolicy,
    *,
    filename: str,
    declared_content_type: str,
    head: bytes,
    size: int,
) -> UploadVerdict:
    """Validate an upload against ``policy`` («проверка загрузки»).

    Checks run cheapest-first: size → content-type allowlist → magic prefix.
    Returns an :class:`UploadVerdict`; ``ok`` is ``True`` only on a full pass.
    """
    safe = sanitize_filename(filename)
    if size > policy.max_bytes:
        return UploadVerdict(status=413, ok=False, reason="too_large", safe_filename=safe)
    if declared_content_type not in policy.allowed_content_types:
        return UploadVerdict(status=415, ok=False, reason="content_type", safe_filename=safe)
    signatures = policy.magic_signatures.get(declared_content_type)
    if signatures and not any(head.startswith(sig) for sig in signatures):
        return UploadVerdict(status=415, ok=False, reason="magic_mismatch", safe_filename=safe)
    return UploadVerdict(status=200, ok=True, reason="ok", safe_filename=safe)
