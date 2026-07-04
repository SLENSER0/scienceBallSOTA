"""Tests for the §4.7 cache wiring in :mod:`kg_retrievers.embeddings`.

Полностью офлайн: реальная модель (fastembed/sentence-transformers) НЕ грузится —
``embeddings._model`` подменяется детерминированным фейком, считающим свои вызовы.
Так мы доказываем, что кэш *поведение сохраняет* (тот же результат, что у прямого
``model.encode`` на нормализованных текстах) и лишь ЭКОНОМИТ forward pass:

* повторные/дублирующие тексты считаются моделью один раз;
* повторный вызов ``embed`` тем же текстом модель не трогает;
* порядок и значения на выходе идентичны, а объекты-списки на каждой позиции свои;
* опциональный on-disk слой (по умолчанию выключен) переживает «рестарт» процесса.
"""

from __future__ import annotations

import pytest

from kg_retrievers import embeddings


class FakeModel:
    """Deterministic stand-in for a loaded embedding backend, counting encode calls."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, docs: list[str]) -> list[list[float]]:
        self.calls.append(list(docs))
        # Deterministic per text (as a real model is), 2-d so equality is meaningful.
        return [[float(len(d)), float(sum(ord(c) for c in d) % 97)] for d in docs]

    @property
    def n_encoded(self) -> int:
        """Total texts pushed through the model across all batches."""
        return sum(len(batch) for batch in self.calls)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    """Install a fresh FakeModel as the active backend and reset all cache state."""
    model = FakeModel()
    monkeypatch.setattr(embeddings, "_model", lambda: model)
    embeddings.embedding_cache().clear()
    # Reset the optional on-disk singleton so tests never share a file/connection.
    monkeypatch.setattr(embeddings, "_DISK_CACHE", None, raising=False)
    monkeypatch.setattr(embeddings, "_DISK_CACHE_MODEL", None, raising=False)
    yield model
    embeddings.embedding_cache().clear()


# ---------------------------------------------------------------------------
# In-process cache — dedup, reuse, order/value preservation (behavior-preserving)
# ---------------------------------------------------------------------------


def test_embed_dedups_duplicates_within_one_call(fake: FakeModel) -> None:
    """Duplicate texts in one call are embedded once, yet every position is filled."""
    out = embeddings.embed(["a", "b", "a", "b"])
    assert len(out) == 4
    # Model saw each unique text exactly once, in first-seen order, in ONE batch.
    assert fake.calls == [["a", "b"]]
    assert out[0] == out[2] and out[1] == out[3]
    assert out[0] != out[1]


def test_embed_positions_are_distinct_list_objects(fake: FakeModel) -> None:
    """Each output position is its own list (like model.encode), even for duplicates."""
    out = embeddings.embed(["dup", "dup"])
    assert out[0] == out[1]
    assert out[0] is not out[1]  # mutating one must not touch the other
    out[0].append(999.0)
    assert out[1] == [3.0, float(sum(ord(c) for c in "dup") % 97)]


def test_embed_reuses_cache_across_calls(fake: FakeModel) -> None:
    """A text embedded once is served from cache on the next call (model not re-run)."""
    first = embeddings.embed(["query"])
    second = embeddings.embed(["query"])
    assert first == second
    assert fake.calls == [["query"]]  # exactly one model batch total


def test_embed_only_misses_reach_the_model(fake: FakeModel) -> None:
    """A second call recomputes only the never-seen text; cached ones are reused."""
    embeddings.embed(["x", "y"])
    fake.calls.clear()
    out = embeddings.embed(["x", "z", "y"])
    assert fake.calls == [["z"]]  # only the new text 'z' hit the model
    assert out == embeddings.embed(["x", "z", "y"])  # stable, order preserved


def test_embed_matches_uncached_model_output(fake: FakeModel) -> None:
    """Cached embed() == a direct model.encode() on the normalized docs (same result)."""
    texts = ["обратный осмос", "", "  ", "abc", "abc"]
    normalized = [t if t.strip() else " " for t in texts]
    reference = FakeModel().encode(normalized)  # what the uncached path would return
    assert embeddings.embed(texts) == reference


def test_embed_empty_input_returns_empty(fake: FakeModel) -> None:
    """No texts → no vectors and the model is never invoked."""
    assert embeddings.embed([]) == []
    assert fake.calls == []


def test_embed_blank_texts_collapse_to_single_compute(fake: FakeModel) -> None:
    """'' and whitespace both normalize to ' ' → one shared compute, equal vectors."""
    out = embeddings.embed(["", "  ", "\t"])
    assert fake.calls == [[" "]]  # all three normalized to the same single text
    assert out[0] == out[1] == out[2]


def test_embed_one_delegates_to_embed(fake: FakeModel) -> None:
    """embed_one returns the single vector; a blank text still yields a real vector."""
    assert embeddings.embed_one("solo") == embeddings.embed(["solo"])[0]


# ---------------------------------------------------------------------------
# Optional on-disk cache (§4.7) — off by default, survives a simulated restart
# ---------------------------------------------------------------------------


def test_disk_disabled_by_default_no_io(fake: FakeModel, monkeypatch: pytest.MonkeyPatch) -> None:
    """With the flag unset, _disk_cache() is None and embed() touches no disk."""
    monkeypatch.delenv("KG_EMBED_DISK_CACHE", raising=False)
    assert embeddings._disk_cache() is None
    embeddings.embed(["p"])  # must not raise / create any store
    assert embeddings._DISK_CACHE is None


def test_disk_cache_round_trip(tmp_path) -> None:
    """_DiskCache persists and returns exactly the vectors it was given."""
    dc = embeddings._DiskCache(str(tmp_path / "rt.sqlite"))
    dc.put_many([("k1", [1.0, 2.0]), ("k2", [3.5, 4.5])])
    got = dc.get_many(["k1", "k2", "absent"])
    assert got == {"k1": [1.0, 2.0], "k2": [3.5, 4.5]}  # miss simply omitted


def test_disk_path_is_namespaced_by_model(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The on-disk file name embeds a slug of the model, so a swap can't alias it."""
    monkeypatch.setenv("KG_EMBED_DISK_CACHE_DIR", str(tmp_path))
    p_a = embeddings._disk_path("ibm-granite/granite-embedding-97m")
    p_b = embeddings._disk_path("ibm-granite/granite-embedding-311m")
    assert p_a != p_b
    assert p_a.endswith(".sqlite") and "granite-embedding-97m" in p_a


def test_disk_cache_survives_restart(
    fake: FakeModel, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """After a 'restart' (cold in-process cache) a persisted text skips the model."""
    monkeypatch.setenv("KG_EMBED_DISK_CACHE", "1")
    monkeypatch.setenv("KG_EMBED_DISK_CACHE_DIR", str(tmp_path))

    warm = embeddings.embed(["persist-me"])
    assert fake.calls == [["persist-me"]]  # computed + persisted this run

    # Simulate a process restart: cold in-process LRU and a re-opened disk handle,
    # but the SQLite file on disk remains.
    embeddings.embedding_cache().clear()
    monkeypatch.setattr(embeddings, "_DISK_CACHE", None)
    monkeypatch.setattr(embeddings, "_DISK_CACHE_MODEL", None)
    fake.calls.clear()

    cold = embeddings.embed(["persist-me"])
    assert cold == warm  # identical vector after restart
    assert fake.calls == []  # served from disk — the model never ran
