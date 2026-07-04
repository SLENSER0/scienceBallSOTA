"""Thin OpenRouter LLM client (OSS models only — ADR-0006).

Wraps the OpenAI-compatible OpenRouter endpoint. Provides plain-text and
JSON-structured completion with fence-stripping and retry. Model IDs come from
``Settings`` (defaults are Apache-2.0 / MIT).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("llm")
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

# OSS allowlist enforced defensively (substring match on provider/family).
OSS_ALLOWED_PREFIXES = (
    "qwen/",
    "deepseek/",
    "mistralai/",
    "microsoft/",
    "nvidia/",
    "cognitivecomputations/",
    "nousresearch/",
    "thudm/",
    "01-ai/",
    "z-ai/",  # Zhipu GLM (GLM-4.5/4.6/5.x — MIT open weights)
    "zhipu/",  # Zhipu alt namespace
    "minimax/",  # MiniMax-M* (Apache-2.0 open weights) — multimodal
    "ibm-granite/",  # IBM Granite (Apache-2.0) — embeddings/rerank
    "moonshotai/",  # Kimi (Apache-2.0)
)
OSS_BLOCKED = (
    "meta-llama/",
    "google/gemma",
    "anthropic/",
    "openai/",
    "google/gemini",
    "x-ai/",
    "cohere/",
)


def is_oss_model(model: str) -> bool:
    m = model.lower()
    if any(m.startswith(b) or b in m for b in OSS_BLOCKED):
        return False
    return any(m.startswith(p) for p in OSS_ALLOWED_PREFIXES)


class LLMClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        from openai import OpenAI

        s = get_settings()
        key = api_key or s.llm_api_key.get_secret_value()
        self._client = OpenAI(
            base_url=base_url or s.llm_api_base,
            api_key=key or "missing",
            timeout=s.llm_timeout_s,
            max_retries=s.llm_max_retries,
            default_headers={
                "HTTP-Referer": "https://github.com/SLENSER0/scienceBallSOTA",
                "X-Title": "Nauchny Klubok",
            },
        )
        self._settings = s
        self.used_models: list[str] = []

    def complete(
        self,
        user: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 1200,
    ) -> str:
        mdl = model or self._settings.llm_model_extract
        if not is_oss_model(mdl):
            raise ValueError(f"Model '{mdl}' is not on the OSS allowlist (ADR-0006).")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = self._client.chat.completions.create(
            model=mdl,
            messages=messages,  # type: ignore[arg-type]
            temperature=self._settings.llm_temperature if temperature is None else temperature,
            max_tokens=max_tokens,
        )
        self.used_models.append(mdl)
        return (resp.choices[0].message.content or "").strip()

    def complete_stream(
        self,
        user: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 1600,
    ) -> Iterator[str]:
        """Yield answer text deltas as the model generates them (OpenAI stream=True).

        Lets a caller surface a brief conclusion in seconds and fill in the rest live,
        instead of blocking ~15 s for the whole completion.
        """
        mdl = model or self._settings.llm_model_synth
        if not is_oss_model(mdl):
            raise ValueError(f"Model '{mdl}' is not on the OSS allowlist (ADR-0006).")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        stream = self._client.chat.completions.create(
            model=mdl,
            messages=messages,  # type: ignore[arg-type]
            temperature=self._settings.llm_temperature if temperature is None else temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body={"provider": {"sort": "throughput", "allow_fallbacks": True}},
        )
        self.used_models.append(mdl)
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            piece = getattr(delta, "content", None) if delta else None
            if piece:
                yield piece

    def complete_with_reasoning(
        self,
        user: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 2000,
    ) -> tuple[str, str]:
        """Like :meth:`complete` but also returns the model's reasoning trace.

        Reasoning-capable OSS models (DeepSeek-V4-Flash, GLM-5.2) expose their
        chain-of-thought in ``message.reasoning`` — we surface it so the UI can
        show a «thinking» panel. Non-reasoning models simply return an empty trace.
        """
        mdl = model or self._settings.llm_model_synth
        if not is_oss_model(mdl):
            raise ValueError(f"Model '{mdl}' is not on the OSS allowlist (ADR-0006).")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = self._client.chat.completions.create(
            model=mdl,
            messages=messages,  # type: ignore[arg-type]
            temperature=self._settings.llm_temperature if temperature is None else temperature,
            max_tokens=max_tokens,
            extra_body={"provider": {"sort": "throughput", "allow_fallbacks": True}},
        )
        self.used_models.append(mdl)
        msg = resp.choices[0].message
        content = (getattr(msg, "content", "") or "").strip()
        reasoning = (getattr(msg, "reasoning", "") or "").strip()
        return content, reasoning

    def complete_multimodal(
        self,
        user: str,
        images: list[str],
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 1500,
    ) -> str:
        """Vision completion — analyse image(s) alongside a text prompt.

        ``images`` are ``data:`` URIs or ``http(s)`` URLs. Routed to the
        multimodal OSS model (MiniMax-M3) via OpenRouter's vision content format
        (``image_url`` parts). Used by multimodal deep-research to read figures,
        micrographs, flowsheets and screenshots.
        """
        mdl = model or self._settings.deep_research_multimodal_model
        if not is_oss_model(mdl):
            raise ValueError(f"Model '{mdl}' is not on the OSS allowlist (ADR-0006).")
        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        resp = self._client.chat.completions.create(
            model=mdl,
            messages=messages,  # type: ignore[arg-type]
            temperature=self._settings.llm_temperature,
            max_tokens=max_tokens,
            extra_body={"provider": {"sort": "throughput", "allow_fallbacks": True}},
        )
        self.used_models.append(mdl)
        return (resp.choices[0].message.content or "").strip()

    def complete_json(
        self,
        user: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 1600,
        retries: int = 2,
    ) -> Any:
        """Return parsed JSON. Retries once asking the model to fix invalid JSON."""
        sys = (system or "") + "\nОтвечай ТОЛЬКО валидным JSON без пояснений и markdown."
        last = ""
        for attempt in range(retries + 1):
            raw = self.complete(
                user
                if attempt == 0
                else f"{user}\n\nПредыдущий ответ не был валидным JSON:\n{last}\n"
                "Верни ТОЛЬКО корректный JSON.",
                system=sys,
                model=model,
                max_tokens=max_tokens,
            )
            parsed = _try_parse_json(raw)
            if parsed is not None:
                return parsed
            last = raw
            _log.warning("llm.json_parse_retry", attempt=attempt)
        raise ValueError(f"LLM did not return valid JSON after {retries + 1} tries: {last[:200]}")


def _try_parse_json(text: str) -> Any:
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    for candidate in (text, _first_brace_block(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _first_brace_block(text: str) -> str | None:
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


_shared: LLMClient | None = None


def get_llm() -> LLMClient:
    global _shared
    if _shared is None:
        _shared = LLMClient()
    return _shared
