"""A free (OSS) web-search tool for open_deep_research (§5 / library).

open_deep_research's built-in search backends are Tavily (paid), OpenAI/Anthropic
native web search, or ``none``. To run *real* deep research (with real source URLs
in the citations) under our OSS-only, no-paid-key policy (§7.5), we give it a
DuckDuckGo-backed ``web_search`` tool (``ddgs``, free, no API key) exposing the same
``queries: list[str]`` interface. The runner monkeypatches ODR's ``get_search_tool``
to return this tool, so the vendored repo stays pristine.
"""

from __future__ import annotations

import contextvars
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

_DESC = (
    "Search the web for scientific sources. Accepts a list of search queries and "
    "returns titled results with real URLs and snippets to cite."
)

# Per-run collector of the structured hits the model saw, so the runner can offer a
# machine-readable list of found sources for the «Загрузить в граф» button. Holds a
# shared list set by ``reset_found_sources`` before a run; ``_ddg_search`` appends to
# it (the same list object is visible across the search thread), and ``collected_sources``
# reads it back, deduped by URL.
_FOUND_SOURCES: contextvars.ContextVar[list[dict[str, str]] | None] = contextvars.ContextVar(
    "sb_found_sources", default=None
)


def reset_found_sources() -> None:
    """Start a fresh per-run source collector (call before running deep research)."""
    _FOUND_SOURCES.set([])


def collected_sources() -> list[dict[str, str]]:
    """The structured sources found during the current run, deduped by URL."""
    got = _FOUND_SOURCES.get()
    if not got:
        return []
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for h in got:
        url = h.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(h)
    return out


def _ddg_search(queries: list[str], max_results: int) -> str:
    """Run each query on DuckDuckGo, return a formatted, citable results block."""
    from ddgs import DDGS

    from kg_common import get_logger

    get_logger("deep-search").info("web_search.call", queries=queries[:3], n=len(queries))
    blocks: list[str] = []
    with DDGS() as ddg:
        for q in queries:
            blocks.append(f"## Запрос: {q}")
            try:
                hits = list(ddg.text(q, max_results=max_results))
            except Exception as exc:
                blocks.append(f"(поиск не удался: {type(exc).__name__})")
                continue
            if not hits:
                blocks.append("(результатов нет)")
            collector = _FOUND_SOURCES.get()
            for i, h in enumerate(hits, 1):
                title = h.get("title", "").strip()
                url = h.get("href") or h.get("url") or ""
                body = (h.get("body") or "").strip()[:300]
                blocks.append(f"{i}. {title}\n   URL: {url}\n   {body}")
                if collector is not None and url:
                    collector.append({"title": title, "url": url, "snippet": body, "query": q})
    return "\n".join(blocks) or "(нет результатов)"


@tool(description=_DESC)
async def web_search(
    queries: list[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    config: Annotated[dict | None, InjectedToolArg] = None,
) -> str:
    """DuckDuckGo web search returning real titled URLs + snippets (free, no key)."""
    import anyio

    n = max(1, min(int(max_results or 5), 8))
    return await anyio.to_thread.run_sync(lambda: _ddg_search(queries, n))


web_search.metadata = {"type": "search", "name": "web_search"}


async def ddg_search_tool(_search_api: object = None) -> list:
    """Drop-in replacement for open_deep_research ``get_search_tool`` (async)."""
    return [web_search]
