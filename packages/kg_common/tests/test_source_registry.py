"""Source registry (§5.4)."""

from __future__ import annotations

import pytest

from kg_common.storage.source_registry import Source, SourceRegistry


@pytest.fixture
def reg() -> SourceRegistry:
    r = SourceRegistry("sqlite:///:memory:")
    r.migrate()
    return r


def test_register_and_get(reg: SourceRegistry) -> None:
    reg.register(
        Source(
            "src:1",
            uri="minio://raw/a.pdf",
            title="Отчёт",
            doc_type="internal_report",
            license="proprietary",
            sha256="abc",
            country="russia",
            n_chunks=12,
        )
    )
    s = reg.get("src:1")
    assert s is not None and s.title == "Отчёт" and s.n_chunks == 12
    assert reg.exists("abc") and reg.by_hash("abc").source_id == "src:1"


def test_register_is_idempotent_upsert(reg: SourceRegistry) -> None:
    reg.register(Source("src:1", sha256="h", status="registered", n_chunks=0))
    reg.register(Source("src:1", sha256="h", status="ingested", n_chunks=30))  # update
    assert len(reg.list()) == 1
    assert reg.get("src:1").status == "ingested" and reg.get("src:1").n_chunks == 30


def test_dedup_by_content_hash(reg: SourceRegistry) -> None:
    reg.register(Source("src:1", sha256="dup"))
    assert reg.exists("dup")
    assert not reg.exists("other")


def test_filters_and_license_counts(reg: SourceRegistry) -> None:
    reg.register(Source("s1", doc_type="article", license="CC-BY", sha256="1"))
    reg.register(Source("s2", doc_type="article", license="CC-BY", sha256="2"))
    reg.register(Source("s3", doc_type="patent", license="public", sha256="3"))
    assert len(reg.list(doc_type="article")) == 2
    assert reg.counts_by_license() == {"CC-BY": 2, "public": 1}
