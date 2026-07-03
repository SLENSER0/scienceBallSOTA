"""Spec-exact §11.2 GraphRAG ``settings.yaml`` validator (pure python, no store).

RU: Валидатор конфигурации GraphRAG (§11.2). Проверяет, что словарь настроек
(обычно загруженный из ``settings.yaml``) содержит обязательные секции и что
ключевые параметры согласованы с ожидаемыми значениями пайплайна: модель
эмбеддингов, размер чанка и перекрытие, а также параметры кластеризации графа.
Ошибки (``errors``) делают отчёт невалидным (``ok=False``); предупреждения
(``warnings``) допустимы и на ``ok`` не влияют.
EN: GraphRAG settings validator (§11.2). Checks that a settings mapping (usually
loaded from ``settings.yaml``) has the required sections and that the key knobs
agree with the pipeline's expectations: embedding model, chunk size / overlap and
the graph-clustering parameters. ``errors`` make the report invalid (``ok=False``);
``warnings`` are tolerated and do not affect ``ok``.

Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()``; this module never touches a store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# §11.2 required top-level sections of a GraphRAG ``settings.yaml``.
REQUIRED_KEYS: tuple[str, ...] = (
    "llm",
    "embeddings",
    "chunks",
    "community_reports",
    "cluster_graph",
)


@dataclass(frozen=True)
class SettingsReport:
    """Immutable result of :func:`validate_settings` (§11.2).

    ``ok`` is ``True`` iff ``errors`` is empty (warnings are allowed). The echoed
    ``embedding_model`` / ``chunk_size`` / ``chunk_overlap`` reflect what was read
    from the settings (best effort; ``''``/``0`` when the value was absent or not
    an int). ``errors`` and ``warnings`` are ordered, human-readable messages.
    """

    ok: bool
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Return a plain-dict view (copies the message lists) for JSON/logging."""
        return {
            "ok": self.ok,
            "embedding_model": self.embedding_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _as_int(value: object, default: int = 0) -> int:
    """Coerce ``value`` to ``int`` (bools excluded); return ``default`` otherwise."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def validate_settings(
    settings: dict,
    *,
    expected_embedding_model: str,
    expected_chunk_size: int,
) -> SettingsReport:
    """Validate a GraphRAG ``settings`` mapping against pipeline expectations (§11.2).

    Checks performed:
      * every key in :data:`REQUIRED_KEYS` is present (else one error each);
      * ``settings['embeddings']['model'] == expected_embedding_model`` — else the
        error ``'embedding model mismatch'`` (a missing model reads as ``''`` and
        still just yields the error, never a crash);
      * ``chunks.size == expected_chunk_size`` — else a *warning* (not an error);
      * ``chunks.overlap < chunks.size`` — else the error ``'chunk overlap >= size'``;
      * ``cluster_graph.max_cluster_size > 0`` — else an error.

    ``ok`` is ``True`` iff no errors were collected. All lookups are defensive so a
    malformed / partial mapping produces messages instead of raising.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in settings:
            errors.append(f"missing required key '{key}'")

    embeddings = settings.get("embeddings") or {}
    embedding_model = ""
    if isinstance(embeddings, dict):
        raw_model = embeddings.get("model", "")
        embedding_model = raw_model if isinstance(raw_model, str) else str(raw_model)
    if embedding_model != expected_embedding_model:
        errors.append(
            f"embedding model mismatch: expected {expected_embedding_model!r}, "
            f"got {embedding_model!r}"
        )

    chunks = settings.get("chunks") or {}
    chunk_size = _as_int(chunks.get("size")) if isinstance(chunks, dict) else 0
    chunk_overlap = _as_int(chunks.get("overlap")) if isinstance(chunks, dict) else 0
    if chunk_size != expected_chunk_size:
        warnings.append(f"chunk size {chunk_size} differs from expected {expected_chunk_size}")
    if chunk_overlap >= chunk_size:
        errors.append(f"chunk overlap >= size: overlap {chunk_overlap} >= size {chunk_size}")

    cluster_graph = settings.get("cluster_graph") or {}
    max_cluster_size = (
        _as_int(cluster_graph.get("max_cluster_size")) if isinstance(cluster_graph, dict) else 0
    )
    if max_cluster_size <= 0:
        errors.append(f"cluster_graph.max_cluster_size must be > 0, got {max_cluster_size}")

    return SettingsReport(
        ok=not errors,
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        errors=errors,
        warnings=warnings,
    )
