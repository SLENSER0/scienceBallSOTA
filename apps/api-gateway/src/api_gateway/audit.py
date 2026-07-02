"""Append-only audit log (§24.14): who did what, when.

Logs queries / views / exports / graph edits to ``var/audit.jsonl`` (structured,
tamper-evident by append-only convention). Read back via /admin/audit.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from kg_common import get_logger, get_settings

_log = get_logger("audit")


def _audit_path() -> Path:
    return Path(get_settings().runtime_dir) / "audit.jsonl"


def record(action: str, *, user: str, role: str, detail: dict | None = None) -> None:
    entry = {
        "ts": int(time.time()),
        "user": user,
        "role": role,
        "action": action,
        "detail": detail or {},
    }
    try:
        p = _audit_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        _log.warning("audit.write_failed", error=str(exc)[:100])


def tail(limit: int = 100) -> list[dict]:
    p = _audit_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
