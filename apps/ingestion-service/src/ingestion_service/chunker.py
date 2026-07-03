"""Section-aware text chunking (§5.9).

Splits pages into chunks that respect document structure instead of cutting at a
fixed byte offset: headings (markdown ``#``, numbered ``1.2``, known section
keywords, short UPPER-CASE lines) start new sections, and body text is packed
into ≤``size`` chunks at *sentence* boundaries (with overlap), hard-splitting only
a single sentence longer than ``size``. Each ``Chunk`` carries its ``section_path``
and ``chunk_type`` for provenance + retrieval. Backward-compatible: callers that
only read ``index/page/text/char_start`` are unaffected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_WS = re.compile(r"[ \t]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_HEADING_KW = re.compile(
    r"^(аннотац|введен|материалы и методы|методик|методы|результат|обсужден|"
    r"заключен|выводы|список литератур|литератур|abstract|introduction|"
    r"methods?|materials and methods|results?|discussion|conclusions?|references)\b",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    index: int
    page: int
    text: str
    char_start: int
    section_path: list[str] = field(default_factory=list)
    chunk_type: str = "text"


def _is_heading(line: str) -> tuple[bool, int]:
    """(is_heading, depth). Depth 1 = top-level section."""
    s = line.strip()
    if not s or len(s) > 120:
        return False, 0
    m = re.match(r"^(#{1,6})\s+\S", s)
    if m:
        return True, len(m.group(1))
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+\S", s)  # "1. Введение" / "2.3 Методы"
    if m:
        return True, m.group(1).count(".") + 1
    if _HEADING_KW.match(s) and len(s) <= 70:
        return True, 1
    if s.isupper() and 3 <= len(s) <= 70:
        return True, 1
    return False, 0


def _pack(text: str, size: int, overlap: int) -> list[str]:
    """Pack sentences into ≤size pieces; hard-split a lone oversized sentence."""
    out: list[str] = []
    cur = ""
    for sent in (s.strip() for s in _SENT_SPLIT.split(text) if s.strip()):
        if len(sent) > size:
            if cur:
                out.append(cur)
                cur = ""
            step = max(1, size - overlap)
            out.extend(sent[i : i + size] for i in range(0, len(sent), step))
            continue
        if cur and len(cur) + 1 + len(sent) > size:
            out.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = f"{tail} {sent}".strip()
        else:
            cur = f"{cur} {sent}".strip() if cur else sent
    if cur:
        out.append(cur)
    return [c for c in out if len(c.strip()) >= 40]


def chunk_pages(pages: list[tuple[int, str]], size: int = 2200, overlap: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    stack: list[tuple[int, str]] = []  # (depth, title) — a heading replaces same/deeper levels

    for page_no, raw in pages:
        buf: list[str] = []

        def flush(cur_buf: list[str], page_no: int = page_no, raw: str = raw) -> None:
            nonlocal idx
            body = _WS.sub(" ", " ".join(cur_buf)).strip()
            if not body:
                return
            offset = max(0, raw.find(cur_buf[0][:30])) if cur_buf else 0
            path = [title for _, title in stack]
            for piece in _pack(body, size, overlap):
                chunks.append(
                    Chunk(
                        index=idx, page=page_no, text=piece, char_start=offset,
                        section_path=list(path), chunk_type="text",
                    )
                )
                idx += 1

        for line in raw.splitlines():
            is_head, depth = _is_heading(line)
            if is_head:
                flush(buf)
                buf = []
                while stack and stack[-1][0] >= depth:  # pop same/deeper → siblings replace
                    stack.pop()
                stack.append((depth, re.sub(r"^#+\s*", "", line.strip())))
            elif line.strip():
                buf.append(line.strip())
        flush(buf)
    return chunks
