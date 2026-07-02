"""Topic subscriptions + notification generation (§24.16).

File-backed subscriptions (``var/subscriptions.jsonl``); notifications are
computed on demand by matching a subscription's topic against the graph
(new-ish papers, gaps, contradictions), respecting the caller's access role.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("subscriptions")
_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _path() -> Path:
    return Path(get_settings().runtime_dir) / "subscriptions.jsonl"


def _load() -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _save(subs: list[dict[str, Any]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in subs) + "\n", encoding="utf-8"
    )


def subscribe(user: str, topic: str, channels: list[str] | None = None) -> dict[str, Any]:
    subs = _load()
    sid = f"sub:{uuid.uuid5(_NS, f'{user}|{topic}')}"
    sub = {
        "id": sid,
        "user": user,
        "topic": topic,
        "channels": channels or ["in_app"],
        "created_at": int(time.time()),
    }
    subs = [s for s in subs if s["id"] != sid] + [sub]
    _save(subs)
    return sub


def list_for(user: str) -> list[dict[str, Any]]:
    return [s for s in _load() if s["user"] == user]


def notifications_for(user: str, store, role: str = "researcher") -> list[dict[str, Any]]:
    """Compute notifications for a user's subscriptions (topic → graph matches)."""
    from agent_service.access import apply_access_policy

    from kg_extractors.query_parser import parse_query
    from kg_retrievers.graph_retriever import GraphRetriever

    out: list[dict[str, Any]] = []
    retriever = GraphRetriever(store)
    for sub in list_for(user):
        intent = parse_query(sub["topic"])
        res = apply_access_policy(retriever.retrieve(intent), role)
        events: list[str] = []
        if res.contradictions:
            events.append(f"⚠ {len(res.contradictions)} противоречие(й)")
        if res.gaps:
            events.append(f"🔍 {len(res.gaps)} пробел(ов)")
        n_sources = sum(1 for e in res.evidence if e.get("id") != "restricted:notice")
        if n_sources:
            events.append(f"📄 {n_sources} источник(ов)")
        if events:
            out.append(
                {
                    "subscription_id": sub["id"],
                    "topic": sub["topic"],
                    "summary": "; ".join(events),
                    "solutions": [s.get("name") for s in res.solutions[:5]],
                }
            )
    return out
