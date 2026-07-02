"""Export answers/subgraphs to Markdown / JSON / JSON-LD (§24.16 / §24.19)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/export", tags=["export"])

JSONLD_CONTEXT = {
    "@vocab": "https://science-ball.example/ontology#",
    "kg": "https://science-ball.example/ontology#",
    "schema": "https://schema.org/",
    "name": "schema:name",
    "evidence": "kg:evidence",
    "confidence": "kg:confidence",
}


class ExportRequest(BaseModel):
    query: str
    role: str = "researcher"
    format: str = "markdown"  # markdown | json | jsonld
    use_llm: bool = True


@router.post("")
def export(req: ExportRequest):  # type: ignore[no-untyped-def]
    from agent_service.agent import answer_query

    ans = answer_query(req.query, get_store(), role=req.role, use_llm=req.use_llm)

    if req.format == "markdown":
        md = _to_markdown(req.query, ans)
        return PlainTextResponse(md, media_type="text/markdown")
    if req.format == "jsonld":
        return _to_jsonld(ans)
    return ans.model_dump(by_alias=True)


def _to_markdown(query: str, ans) -> str:  # type: ignore[no-untyped-def]
    parts = [f"# Отчёт: {query}\n", ans.answer_markdown, "\n## Источники\n"]
    for c in ans.citations:
        ev = c.evidence
        parts.append(
            f"- {c.marker} {c.source_title or ''} "
            f"(стр. {ev.page}, {ev.evidence_strength or ''}, conf {ev.confidence})"
        )
    parts.append(
        f"\n_Достоверность ответа: {ans.confidence}. "
        f"Модели (OSS): {', '.join(ans.used_models) or 'deterministic'}._"
    )
    return "\n".join(parts)


def _to_jsonld(ans):  # type: ignore[no-untyped-def]
    nodes = []
    if ans.graph:
        for n in ans.graph.nodes:
            nodes.append(
                {
                    "@id": f"kg:{n.id}",
                    "@type": n.type,
                    "name": n.label,
                    "confidence": n.confidence,
                }
            )
    return {
        "@context": JSONLD_CONTEXT,
        "@type": "kg:AnswerReport",
        "answer": ans.answer_markdown,
        "confidence": ans.confidence,
        "graph": nodes,
        "citations": [
            {
                "@id": f"kg:{c.evidence.evidence_id}",
                "text": c.evidence.text,
                "confidence": c.evidence.confidence,
            }
            for c in ans.citations
        ],
    }
