"""Runs the real open_deep_research graph, wired to our OSS LLM (§5 / library).

This integrates the *actual* ``open_deep_research.deep_researcher`` CompiledStateGraph
(vendored at ``third_party/open_deep_research``, MIT) — not a re-implementation. We
only supply configuration so its LangGraph pipeline (clarify → research brief →
supervisor → researcher → final report) runs on our OSS model via OpenRouter
(OpenAI-compatible) with ``search_api="none"`` (no paid Tavily; OSS-only, §7.5).

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


def _configurable() -> dict[str, Any]:
    """Point open_deep_research at our OSS model + disable paid web search."""
    s = get_settings()
    model = f"openai:{s.llm_model_synth}"  # OpenRouter model id, OpenAI-compatible
    return {
        "research_model": model,
        "summarization_model": model,
        "compression_model": model,
        "final_report_model": model,
        "search_api": "none",  # OSS-only: no Tavily/paid search
        "allow_clarification": False,  # headless run: don't block on a clarify turn
        "max_researcher_iterations": 1,
        "max_concurrent_research_units": 1,
        "max_react_tool_calls": 2,
        "max_structured_output_retries": 2,
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

    from langchain_core.messages import HumanMessage
    from open_deep_research.deep_researcher import deep_researcher

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
        "engine": "open_deep_research",
        "model": s.llm_model_synth,
    }
