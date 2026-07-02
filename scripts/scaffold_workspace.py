#!/usr/bin/env python3
"""Generate consistent pyproject.toml / __init__.py / py.typed / README for all
Python workspace members (packages/* and apps/*). Idempotent: overwrites only the
scaffold files, never the hand-written logic modules.

Run: python scripts/scaffold_workspace.py
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# name -> (dist_name, import_pkg, kind, deps, description, port)
PACKAGES: dict[str, dict] = {
    "packages/kg_common": dict(
        dist="kg-common",
        pkg="kg_common",
        kind="lib",
        deps=["pydantic>=2.7", "pydantic-settings>=2.2", "structlog>=24.1", "orjson>=3.10"],
        desc="Shared config, DTOs, deterministic IDs, logging, telemetry.",
        port=None,
    ),
    "packages/kg_schema": dict(
        dist="kg-schema",
        pkg="kg_schema",
        kind="lib",
        deps=["pydantic>=2.7", "pyyaml>=6.0", "kg-common"],
        desc="Domain ontology: LinkML source + Pydantic models, labels, relationships, enums.",
        port=None,
    ),
    "packages/kg_extractors": dict(
        dist="kg-extractors",
        pkg="kg_extractors",
        kind="lib",
        deps=[
            "kg-common",
            "kg-schema",
            "openai>=1.40",
            "pint>=0.23",
            "rapidfuzz>=3.9",
            "regex>=2024.5",
        ],
        desc="Rule + LLM + materials extractors, unit normalization, entity resolution.",
        port=None,
    ),
    "packages/kg_retrievers": dict(
        dist="kg-retrievers",
        pkg="kg_retrievers",
        kind="lib",
        deps=[
            "kg-common",
            "kg-schema",
            "kuzu>=0.7",
            "qdrant-client>=1.10",
            "fastembed>=0.3",
            "rank-bm25>=0.2",
            "numpy>=1.26",
        ],
        desc="Graph / vector / keyword / hybrid retrievers + GraphRAG.",
        port=None,
    ),
    "packages/kg_eval": dict(
        dist="kg-eval",
        pkg="kg_eval",
        kind="lib",
        deps=["kg-common", "kg-schema"],
        desc="Evaluation harness: golden datasets, metrics, runner.",
        port=None,
    ),
    "apps/api-gateway": dict(
        dist="api-gateway",
        pkg="api_gateway",
        kind="app",
        deps=[
            "kg-common",
            "kg-schema",
            "kg-retrievers",
            "kg-extractors",
            "fastapi>=0.115",
            "uvicorn[standard]>=0.30",
            "python-multipart>=0.0.9",
            "httpx>=0.27",
            "xlsxwriter>=3.2",
        ],
        desc="FastAPI API gateway: query/graph/search/evidence/export/admin endpoints.",
        port=8000,
    ),
    "apps/agent-service": dict(
        dist="agent-service",
        pkg="agent_service",
        kind="app",
        deps=[
            "kg-common",
            "kg-schema",
            "kg-retrievers",
            "langgraph>=0.2",
            "langchain-core>=0.3",
            "langchain-openai>=0.2",
            "fastapi>=0.115",
            "uvicorn[standard]>=0.30",
        ],
        desc="LangGraph agent service: query planning, retrieval orchestration, synthesis.",
        port=8010,
    ),
    "apps/ingestion-service": dict(
        dist="ingestion-service",
        pkg="ingestion_service",
        kind="app",
        deps=[
            "kg-common",
            "kg-schema",
            "kg-extractors",
            "kg-retrievers",
            "pypdf>=4.2",
            "pdfplumber>=0.11",
            "python-docx>=1.1",
            "python-pptx>=0.6",
            "openpyxl>=3.1",
            "fastapi>=0.115",
            "uvicorn[standard]>=0.30",
        ],
        desc="Document ingestion: parse PDF/DOCX/PPTX/XLSX, chunk, orchestrate extraction+upsert.",
        port=8020,
    ),
    "apps/graph-service": dict(
        dist="graph-service",
        pkg="graph_service",
        kind="app",
        deps=["kg-common", "kg-schema", "kuzu>=0.7"],
        desc="Kuzu-backed graph store: schema/migrations, deterministic upsert, Cypher templates.",
        port=None,
    ),
    "apps/search-service": dict(
        dist="search-service",
        pkg="search_service",
        kind="app",
        deps=["kg-common", "kg-schema", "kg-retrievers"],
        desc="Vector + keyword indexing/search over Qdrant(local) + BM25.",
        port=None,
    ),
    "apps/extraction-service": dict(
        dist="extraction-service",
        pkg="extraction_service",
        kind="app",
        deps=["kg-common", "kg-schema", "kg-extractors"],
        desc="Extraction orchestration worker (rules + LLM + normalization + ER).",
        port=None,
    ),
    "apps/curation-service": dict(
        dist="curation-service",
        pkg="curation_service",
        kind="app",
        deps=["kg-common", "kg-schema", "kuzu>=0.7"],
        desc="Curation workflow, decision history, expert edits, review queue.",
        port=None,
    ),
}

WORKSPACE_DEP_NAMES = {"kg-common", "kg-schema", "kg-extractors", "kg-retrievers", "kg-eval"}

PYPROJECT_TMPL = """[project]
name = "{dist}"
version = "0.1.0"
description = "{desc}"
requires-python = ">=3.12"
readme = "README.md"
dependencies = [
{deps}
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg}"]

[tool.uv.sources]
{sources}
"""


def render(member: str, cfg: dict) -> None:
    d = ROOT / member
    dep_lines = "\n".join(f'    "{dep}",' for dep in cfg["deps"])
    sources = "\n".join(
        f"{dep} = {{ workspace = true }}" for dep in cfg["deps"] if dep in WORKSPACE_DEP_NAMES
    )
    content = PYPROJECT_TMPL.format(
        dist=cfg["dist"], desc=cfg["desc"], deps=dep_lines, pkg=cfg["pkg"], sources=sources
    )
    (d / "pyproject.toml").write_text(content, encoding="utf-8")

    src = d / "src" / cfg["pkg"]
    src.mkdir(parents=True, exist_ok=True)
    init = src / "__init__.py"
    if not init.exists():
        init.write_text(f'"""{cfg["desc"]}"""\n\n__version__ = "0.1.0"\n', encoding="utf-8")
    (src / "py.typed").write_text("", encoding="utf-8")

    readme = d / "README.md"
    port = f"\n\n**Port:** {cfg['port']}" if cfg["port"] else ""
    readme.write_text(f"# {cfg['dist']}\n\n{cfg['desc']}{port}\n", encoding="utf-8")

    tests = d / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "__init__.py").write_text("", encoding="utf-8")


def main() -> None:
    for member, cfg in PACKAGES.items():
        render(member, cfg)
        print("scaffolded", member)


if __name__ == "__main__":
    main()
