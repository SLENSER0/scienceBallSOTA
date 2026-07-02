"""Keyword (BM25) store (§4 / ADR-0005) — in-process replacement for OpenSearch.

Persists a tokenized corpus + payloads to disk; rebuilds BM25 on load. RU/EN
tokenization is lowercase word-splitting (Unicode aware).
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("keyword_store")
_TOK = re.compile(r"[0-9a-zA-Zа-яёА-ЯЁ]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOK.findall(text)]


@dataclass
class KeywordHit:
    id: str
    score: float
    payload: dict[str, Any]


class KeywordStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or get_settings().bm25_path) / "bm25.pkl"
        self.ids: list[str] = []
        self.payloads: list[dict[str, Any]] = []
        self.corpus: list[list[str]] = []
        self._bm25 = None
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = pickle.loads(self.path.read_bytes())
            self.ids = data["ids"]
            self.payloads = data["payloads"]
            self.corpus = data["corpus"]
            self._rebuild()

    def _rebuild(self) -> None:
        from rank_bm25 import BM25Okapi

        self._bm25 = BM25Okapi(self.corpus) if self.corpus else None

    def index(self, items: list[dict[str, Any]]) -> int:
        for it in items:
            self.ids.append(it["id"])
            self.payloads.append({**it.get("payload", {}), "text": it["text"][:1000]})
            self.corpus.append(tokenize(it["text"]))
        self._rebuild()
        return len(items)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(
            pickle.dumps({"ids": self.ids, "payloads": self.payloads, "corpus": self.corpus})
        )

    def search(self, query: str, limit: int = 8) -> list[KeywordHit]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:limit]
        return [
            KeywordHit(id=self.ids[i], score=float(scores[i]), payload=self.payloads[i])
            for i in ranked
            if scores[i] > 0
        ]

    def count(self) -> int:
        return len(self.ids)
