"""Runs the real open_deep_research graph, wired to our OSS LLM (§5 / library).

This integrates the *actual* ``open_deep_research.deep_researcher`` CompiledStateGraph
(vendored at ``third_party/open_deep_research``, MIT) — not a re-implementation. We
supply configuration so its LangGraph pipeline (clarify → research brief → supervisor
→ researcher → final report) runs on our OSS models via OpenRouter (OpenAI-compatible)
and monkeypatch its search tool to a free DuckDuckGo backend (``deep_search_tool``) so
the report cites *real* source URLs — no paid Tavily (OSS-only, §7.5).

The graph is imported lazily so the gateway starts even when the optional package
is absent; ``deep_research_available()`` reports whether it can run.
"""

from __future__ import annotations

import os
from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("deep-research")


def deep_research_available() -> bool:
    """True if the vendored open_deep_research graph can be imported + a key is set."""
    if not get_settings().llm_api_key.get_secret_value():
        return False
    try:
        import open_deep_research.deep_researcher  # noqa: F401
    except Exception:
        return False
    return True


# OpenRouter provider routing: prefer high-throughput (paid) providers so the
# strong OSS tool-callers don't fall back to congested free endpoints (429).
_OR_PROVIDER = {"provider": {"sort": "throughput", "allow_fallbacks": True}}


def _install_free_search() -> None:
    """Patch open_deep_research: free DuckDuckGo search + OpenRouter paid-provider routing.

    ODR ships Tavily(paid)/native/none search — we swap ``get_search_tool`` for a free
    DuckDuckGo backend so real deep research cites real URLs. We also rebuild ODR's
    ``configurable_model`` (and patch ``init_chat_model``) with an OpenRouter
    ``provider: {sort: throughput}`` routing so requests land on reliable paid
    providers instead of rate-limited free ones — all without editing the vendored repo.
    """
    import langchain.chat_models.base as lc_base
    from open_deep_research import deep_researcher as dr
    from open_deep_research import utils as odr_utils

    from api_gateway.deep_search_tool import ddg_search_tool

    odr_utils.get_search_tool = ddg_search_tool  # type: ignore[assignment]
    if hasattr(dr, "get_search_tool"):
        dr.get_search_tool = ddg_search_tool  # type: ignore[assignment]

    # Inject OpenRouter provider routing at the lowest level so EVERY model ODR
    # builds (incl. the configurable_model at runtime) lands on a paid provider.
    if not getattr(lc_base, "_sb_routed", False):
        _real_helper = lc_base._init_chat_model_helper

        def _routed_helper(model: str, *, model_provider=None, **kwargs):  # type: ignore[no-untyped-def]
            kwargs.setdefault("extra_body", dict(_OR_PROVIDER))
            return _real_helper(model, model_provider=model_provider, **kwargs)

        lc_base._init_chat_model_helper = _routed_helper  # type: ignore[assignment]
        lc_base._sb_routed = True  # type: ignore[attr-defined]


def _configurable() -> dict[str, Any]:
    """Point open_deep_research at our OSS models + real (free) web search.

    Model roles (§7.5 OSS-only): the supervisor + researcher share ODR's single
    ``research_model`` → the supervisor model (GLM-5.2, the strategic delegator);
    the worker-style summarization/compression + the final report use the worker /
    report models (DeepSeek-V4-Flash). All configurable via ``DEEP_RESEARCH_*``.
    """
    s = get_settings()
    supervisor = f"openai:{s.deep_research_supervisor_model}"
    worker = f"openai:{s.deep_research_worker_model}"
    report_model = f"openai:{s.deep_research_report_model}"
    return {
        "research_model": supervisor,
        "summarization_model": worker,
        "compression_model": worker,
        "final_report_model": report_model,
        # 'tavily' selects the tool-using code path; our monkeypatch swaps the tool
        # for the free DuckDuckGo backend so citations carry real URLs (§7.5).
        "search_api": "tavily",
        "allow_clarification": False,  # headless run: don't block on a clarify turn
        "max_researcher_iterations": 2,
        "max_concurrent_research_units": 1,
        "max_react_tool_calls": 3,
        "max_structured_output_retries": 3,
    }


async def run_deep_research(question: str) -> dict[str, Any]:
    """Invoke the real open_deep_research graph on ``question``; return the report.

    Raises ``RuntimeError`` if the package/model is unavailable — the caller
    (``routers/research.py``) falls back to the source-catalog planner.
    """
    if not deep_research_available():
        raise RuntimeError("open_deep_research unavailable (package or OSS key missing)")

    s = get_settings()
    # langchain init_chat_model('openai:…') reads these from the environment.
    os.environ.setdefault("OPENAI_BASE_URL", s.llm_api_base)
    os.environ["OPENAI_API_KEY"] = s.llm_api_key.get_secret_value()

    _install_free_search()
    from api_gateway.deep_search_tool import collected_sources, reset_found_sources
    from langchain_core.messages import HumanMessage
    from open_deep_research.deep_researcher import deep_researcher

    reset_found_sources()
    _log.info("deep_research.start", model=s.llm_model_synth)
    result = await deep_researcher.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": _configurable()},
    )
    report = result.get("final_report", "") or ""
    notes = result.get("notes", []) or []
    return {
        "question": question,
        "report": report,
        "notes": notes,
        "sources": collected_sources(),
        "engine": "open_deep_research",
        "model": s.llm_model_synth,
    }


# open_deep_research node → human-readable stage (the reasoning trace the UI shows).
STAGE_LABELS: dict[str, str] = {
    "clarify_with_user": "Уточнение вопроса",
    "write_research_brief": "Формулировка задания",
    "research_supervisor": "Планирование исследования",
    "supervisor": "Координация под-исследований",
    "supervisor_tools": "Делегирование поиска",
    "researcher": "Исследование источников",
    "researcher_tools": "Сбор материала",
    "compress_research": "Сжатие результатов",
    "final_report_generation": "Генерация отчёта",
}


def _reasoning_from_update(node: str, update: dict[str, Any]) -> str:
    """Extract the meaningful reasoning text a node just produced (for the trace)."""
    if not isinstance(update, dict):
        return ""
    if update.get("research_brief"):
        return str(update["research_brief"])
    notes = update.get("notes") or update.get("raw_notes")
    if notes:
        joined = "\n".join(str(n) for n in notes)[:800]
        return joined
    msgs = update.get("messages") or update.get("supervisor_messages")
    if msgs:
        last = msgs[-1]
        content = getattr(last, "content", None) or (
            last.get("content") if isinstance(last, dict) else ""
        )
        if content:
            return str(content)[:800]
    return ""


async def stream_deep_research(question: str):  # type: ignore[no-untyped-def]
    """Async-iterate the REAL open_deep_research graph, yielding SSE-ready events.

    Streams LangGraph ``updates`` (which node ran + its reasoning output) and
    ``messages`` (live LLM tokens) so the UI can show a stage-by-stage reasoning
    trace ending in the final report — the open-webui «thinking» pattern.
    Yields ``(event_type, data_dict)`` tuples.
    """
    if not deep_research_available():
        raise RuntimeError("open_deep_research unavailable")
    s = get_settings()
    os.environ.setdefault("OPENAI_BASE_URL", s.llm_api_base)
    os.environ["OPENAI_API_KEY"] = s.llm_api_key.get_secret_value()

    _install_free_search()
    from api_gateway.deep_search_tool import collected_sources, reset_found_sources
    from langchain_core.messages import HumanMessage
    from open_deep_research.deep_researcher import deep_researcher

    reset_found_sources()
    yield ("stage", {"node": "start", "label": "Запуск open_deep_research (реальный поиск)"})
    final_report = ""
    async for mode, chunk in deep_researcher.astream(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": _configurable()},
        stream_mode=["updates", "messages"],
    ):
        if mode == "updates" and isinstance(chunk, dict):
            for node, update in chunk.items():
                label = STAGE_LABELS.get(node, node)
                yield ("stage", {"node": node, "label": label})
                reasoning = _reasoning_from_update(node, update)
                if reasoning:
                    yield ("reasoning", {"node": node, "text": reasoning})
                if isinstance(update, dict) and update.get("final_report"):
                    final_report = str(update["final_report"])
        elif mode == "messages":
            msg, _meta = chunk if isinstance(chunk, tuple) else (chunk, {})
            token = getattr(msg, "content", "") or ""
            if token:
                yield ("token", {"text": str(token)})
    yield ("report", {"text": final_report})
    yield ("sources", {"items": collected_sources()})
    yield ("done", {"engine": "open_deep_research", "model": s.llm_model_synth})
