"""Untrusted-content prompt isolation envelope (§19.6 prompt injection defence).

Content retrieved from documents, the web or any user-supplied source is
**untrusted** and must never be interpolated raw into an LLM prompt — it could
carry instructions ("ignore previous instructions…") that hijack the model
(«ненадёжный контент нельзя вставлять как инструкции»). This module wraps each
untrusted segment in an explicit, source-labelled fence so the model can tell
system instructions from data. We **wrap, never strip**: no attempt is made to
sanitise the content itself — the isolation is structural, and the model is
told to treat everything inside a fence as inert data.

:class:`UntrustedSegment` is one labelled chunk; :class:`PromptEnvelope` renders
the system prompt followed by every fenced segment. :func:`build_envelope`
assembles one; :func:`fence_collision` flags the escape hazard where a segment's
text already contains the fence token (it could forge an ``<<END …>>`` and break
out of isolation). Pure-python, no third-party dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class UntrustedSegment:
    """One untrusted content chunk with its provenance («ненадёжный сегмент»).

    ``source_id`` identifies where the text came from (doc id, URL, upload) and
    is echoed into the fence label so the model — and any auditor — can trace an
    injected instruction back to its origin. ``text`` is the raw, unsanitised
    content.
    """

    source_id: str
    text: str

    def as_dict(self) -> dict[str, str]:
        """Return a plain-dict view («сериализуемое представление»)."""
        return {"source_id": self.source_id, "text": self.text}


@dataclass(frozen=True)
class PromptEnvelope:
    """System prompt plus fenced untrusted segments («изолирующий конверт»).

    ``system`` is the trusted instruction block; ``segments`` are the untrusted
    chunks; ``fence`` is the token that marks fence boundaries. :meth:`render`
    emits the system prompt first, then each segment wrapped between
    ``<<UNTRUSTED {fence} source=…>>`` and ``<<END {fence}>>`` markers.
    """

    system: str
    segments: tuple[UntrustedSegment, ...]
    fence: str

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly view that roundtrips via :meth:`from_dict`."""
        return {
            "system": self.system,
            "segments": [seg.as_dict() for seg in self.segments],
            "fence": self.fence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> PromptEnvelope:
        """Rebuild an envelope from :meth:`as_dict` output («обратная сборка»)."""
        raw_segments = data["segments"]
        assert isinstance(raw_segments, list)
        segments = tuple(
            UntrustedSegment(source_id=str(s["source_id"]), text=str(s["text"]))
            for s in raw_segments
        )
        return cls(system=str(data["system"]), segments=segments, fence=str(data["fence"]))

    def render(self) -> str:
        """Render system prompt then every source as a labelled fenced block.

        The system text always precedes the segments; an empty ``segments``
        renders the system prompt alone («пустой набор — только системный текст»).
        """
        blocks = [self.system]
        for seg in self.segments:
            blocks.append(
                f"<<UNTRUSTED {self.fence} source={seg.source_id}>>\n"
                f"{seg.text}\n"
                f"<<END {self.fence}>>"
            )
        return "\n".join(blocks)


def build_envelope(
    system_prompt: str,
    sources: Iterable[UntrustedSegment],
    *,
    fence: str,
) -> PromptEnvelope:
    """Assemble a :class:`PromptEnvelope` from a system prompt and sources.

    The ``sources`` iterable is materialised into a tuple so the envelope is
    frozen and re-renderable («материализуем в кортеж»).
    """
    return PromptEnvelope(system=system_prompt, segments=tuple(sources), fence=fence)


def fence_collision(sources: Iterable[UntrustedSegment], fence: str) -> bool:
    """True if any segment text embeds ``fence`` — an isolation-escape hazard.

    A segment whose own text contains the fence token could forge an ``<<END
    {fence}>>`` marker and break out of its block, so callers should rotate the
    fence (or reject the input) when this returns True («риск побега контента»).
    """
    return any(fence in seg.text for seg in sources)
