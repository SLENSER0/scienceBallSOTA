"""Text chunking (§5): split pages into overlapping chunks with page + offset."""

from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")


@dataclass
class Chunk:
    index: int
    page: int
    text: str
    char_start: int


def chunk_pages(pages: list[tuple[int, str]], size: int = 2200, overlap: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for page_no, text in pages:
        text = _WS.sub(" ", text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            piece = text[start : start + size]
            if len(piece.strip()) >= 40:
                chunks.append(Chunk(index=idx, page=page_no, text=piece, char_start=start))
                idx += 1
            if start + size >= len(text):
                break
            start += size - overlap
    return chunks
