"""Central configuration for all Science-Ball services (pydantic-settings).

One ``Settings`` object, populated from environment / ``.env``, is shared by every
service. It carries both the *target* stack (Neo4j/Qdrant/OpenSearch — for the
docker-compose profile) and the *embedded* runtime paths (Kuzu / Qdrant-local /
BM25) that the system actually runs on locally. See
``docs/adr/0005-embedded-runtime-profile.md``.
"""

from __future__ import annotations

import functools
import pathlib

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = three parents up from this file's package dir
# packages/kg_common/src/kg_common/config.py -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]


def _repo_path(*parts: str) -> str:
    return str(_REPO_ROOT.joinpath(*parts))


class Settings(BaseSettings):
    """Runtime settings. Env vars override defaults; secrets use ``SecretStr``."""

    model_config = SettingsConfigDict(
        env_file=(_repo_path(".env"), ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # -- App --------------------------------------------------------------
    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    repo_root: str = Field(default=str(_REPO_ROOT))
    runtime_dir: str = Field(default=_repo_path("var"), alias="RUNTIME_DIR")

    # -- Runtime profile: 'embedded' (Kuzu/qdrant-local/bm25) or 'server' --
    runtime_profile: str = Field(default="embedded", alias="RUNTIME_PROFILE")

    # -- Graph store: Neo4j (server profile) ------------------------------
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(default=SecretStr("password"), alias="NEO4J_PASSWORD")

    # -- Graph store: Kuzu (embedded profile) -----------------------------
    kuzu_db_path: str = Field(default=_repo_path("var", "kuzu", "graph"), alias="KUZU_DB_PATH")

    # -- Vector: Qdrant ---------------------------------------------------
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_path: str = Field(default=_repo_path("var", "qdrant"), alias="QDRANT_PATH")
    qdrant_collection: str = Field(default="kg_chunks", alias="QDRANT_COLLECTION")
    qdrant_entity_collection: str = Field(default="kg_entities", alias="QDRANT_ENTITY_COLLECTION")

    # -- Keyword: OpenSearch (server) / BM25 (embedded) -------------------
    opensearch_url: str = Field(default="http://localhost:9200", alias="OPENSEARCH_URL")
    opensearch_user: str = Field(default="admin", alias="OPENSEARCH_USER")
    opensearch_password: SecretStr = Field(
        default=SecretStr("adminadminadmin"), alias="OPENSEARCH_PASSWORD"
    )
    bm25_path: str = Field(default=_repo_path("var", "bm25"), alias="BM25_PATH")

    # -- Relational / cache / object store --------------------------------
    postgres_dsn: str = Field(
        default="postgresql://kg:kg@localhost:5432/kg_app", alias="POSTGRES_DSN"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_root_user: str = Field(default="minio", alias="MINIO_ROOT_USER")
    minio_root_password: SecretStr = Field(
        default=SecretStr("minio123"), alias="MINIO_ROOT_PASSWORD"
    )
    minio_bucket: str = Field(default="kg-documents", alias="MINIO_BUCKET")

    # -- Ingestion / orchestration ---------------------------------------
    docling_serve_url: str = Field(default="http://localhost:5001", alias="DOCLING_SERVE_URL")
    dagster_url: str = Field(default="http://localhost:3001", alias="DAGSTER_URL")
    data_dir: str = Field(default=_repo_path("data"), alias="DATA_DIR")
    uploads_dir: str = Field(default=_repo_path("var", "uploads"), alias="UPLOADS_DIR")
    artifacts_dir: str = Field(default=_repo_path("var", "artifacts"), alias="ARTIFACTS_DIR")

    # -- LLM / embeddings (OSS-only, OpenRouter) --------------------------
    # NOTE: per hackathon rules only OSS-licensed models are permitted
    # (Apache-2.0 / MIT). See docs/adr/0006-oss-llm-and-licensing.md.
    llm_api_base: str = Field(default="https://openrouter.ai/api/v1", alias="LLM_API_BASE")
    llm_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENROUTER_API_KEY")
    llm_model_extract: str = Field(default="qwen/qwen-2.5-7b-instruct", alias="LLM_MODEL_EXTRACT")
    llm_model_synth: str = Field(default="deepseek/deepseek-chat-v3-0324", alias="LLM_MODEL_SYNTH")
    llm_model_fast: str = Field(default="qwen/qwen-2.5-7b-instruct", alias="LLM_MODEL_FAST")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")
    llm_timeout_s: float = Field(default=90.0, alias="LLM_TIMEOUT_S")

    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL",
    )
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")

    # -- Observability ----------------------------------------------------
    otel_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    mlflow_tracking_uri: str = Field(default="", alias="MLFLOW_TRACKING_URI")
    langsmith_api_key: SecretStr = Field(default=SecretStr(""), alias="LANGSMITH_API_KEY")

    # -- Auth -------------------------------------------------------------
    jwt_secret: SecretStr = Field(default=SecretStr("dev-insecure-change-me"), alias="JWT_SECRET")
    jwt_ttl_minutes: int = Field(default=720, alias="JWT_TTL_MINUTES")

    def path(self, *parts: str) -> pathlib.Path:
        """Resolve a path relative to the repo root."""
        return _REPO_ROOT.joinpath(*parts)

    def ensure_runtime_dirs(self) -> None:
        """Create the embedded-store directories if missing (idempotent)."""
        # Directory-style stores.
        for p in (self.qdrant_path, self.bm25_path, self.artifacts_dir, self.uploads_dir):
            pathlib.Path(p).mkdir(parents=True, exist_ok=True)
        # kuzu_db_path is a DB file Kuzu creates itself — only ensure its parent.
        pathlib.Path(self.kuzu_db_path).parent.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings factory (import once, reuse everywhere)."""
    return Settings()
