"""§4.9 cross-encoder reranker model config (§10.2 Rerank / §7.5 Node 6).

RU: Конфигурация опционального cross-encoder реранкера — какая модель, сколько
top-N кандидатов рерэнкить, включён ли реранк и размер батча инференса. Чистый
python-контейнер настройки (frozen dataclass), без загрузки модели и без обращений
к стору/графу: сам инференс живёт в ``rerank.py`` (§12.9). Дефолт — OSS-модель с
пермиссивной лицензией ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (Apache-2.0, §10.2).
EN: Config for the optional cross-encoder reranker — which model, how many top-N
candidates to rerank, whether reranking is on, and the inference batch size. A pure
python settings container (frozen dataclass); it loads no model and touches no
store/graph (inference lives in ``rerank.py``, §12.9). The default is the permissive
OSS cross-encoder ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (Apache-2.0, §10.2).

:func:`is_permissive_model` checks a name against the allow-list of OSS cross-encoder
families cleared for the OSS-only deployment (§10.2, ADR-0006): the sentence-transformers
``cross-encoder/*`` rerankers, ``BAAI/bge-reranker-*`` and ``mixedbread-ai/mxbai-rerank-*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Defaults (§10.2: cross-encoder, rerank_top_n=50) ------------------------
# Дефолтная модель — пермиссивный OSS cross-encoder (Apache-2.0), см. ADR-0006.
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_TOP_N: int = 50  # rerank_top_n — top-N кандидатов после fusion (§10.2)
DEFAULT_ENABLED: bool = True  # reranker_enabled — реранк включён по умолчанию
DEFAULT_BATCH_SIZE: int = 32  # размер батча инференса cross-encoder (§12.9)

# --- Permissive OSS cross-encoder families (§10.2 / ADR-0006) ----------------
# Префиксы имён моделей, разрешённых для OSS-only деплоя. Матч регистронезависимый
# по префиксу: покрывает всё семейство (напр. любые ms-marco-MiniLM-L-*-v2).
_PERMISSIVE_PREFIXES: tuple[str, ...] = (
    "cross-encoder/",  # sentence-transformers cross-encoders (Apache-2.0)
    "sentence-transformers/",  # ST reranker checkpoints (Apache-2.0)
    "baai/bge-reranker",  # BAAI bge-reranker-* (MIT / Apache-2.0)
    "mixedbread-ai/mxbai-rerank",  # mxbai-rerank-* (Apache-2.0)
)


@dataclass(frozen=True)
class RerankerConfig:
    """Immutable cross-encoder reranker config (§4.9 / §10.2).

    ``model`` — идентификатор модели (HF repo id); ``top_n`` — сколько top-N
    кандидатов рерэнкить (``>= 1``); ``enabled`` — включён ли реранк (при ``False``
    пайплайн отдаёт fusion-порядок, §12.9); ``batch_size`` — размер батча инференса
    (``>= 1``). Валидация выполняется в :meth:`__post_init__`.
    """

    model: str = DEFAULT_RERANKER_MODEL
    top_n: int = DEFAULT_TOP_N
    enabled: bool = DEFAULT_ENABLED
    batch_size: int = DEFAULT_BATCH_SIZE

    def __post_init__(self) -> None:
        if self.top_n < 1:
            raise ValueError(f"top_n must be >= 1, got {self.top_n!r}")
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size!r}")
        if not self.model:
            raise ValueError("model must be a non-empty model id")

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection of the config (§4.9)."""
        return {
            "model": self.model,
            "top_n": self.top_n,
            "enabled": self.enabled,
            "batch_size": self.batch_size,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RerankerConfig:
        """Rebuild from an :meth:`as_dict` projection; missing keys fall back to defaults.

        Любой отсутствующий ключ берёт своё значение по умолчанию, поэтому частичный
        dict (напр. только ``{"enabled": False}``) — валидный вход. Валидация полей
        выполняется конструктором (``top_n``/``batch_size`` ``>= 1``).
        """
        return cls(
            model=d.get("model", DEFAULT_RERANKER_MODEL),
            top_n=int(d.get("top_n", DEFAULT_TOP_N)),
            enabled=bool(d.get("enabled", DEFAULT_ENABLED)),
            batch_size=int(d.get("batch_size", DEFAULT_BATCH_SIZE)),
        )


def default_reranker_config() -> RerankerConfig:
    """Return the default reranker config (§10.2 defaults: ms-marco-MiniLM, top_n=50)."""
    return RerankerConfig()


def is_permissive_model(name: str) -> bool:
    """True if ``name`` is a permissive OSS cross-encoder cleared for deploy (§10.2).

    Матч регистронезависимый по префиксу из :data:`_PERMISSIVE_PREFIXES` (семейства
    ``cross-encoder/*``, ``sentence-transformers/*``, ``BAAI/bge-reranker-*``,
    ``mixedbread-ai/mxbai-rerank-*``). Пустая/чужая (напр. проприетарная ``cohere/*``)
    строка → ``False``.
    """
    if not name:
        return False
    normalized = name.strip().lower()
    return any(normalized.startswith(prefix) for prefix in _PERMISSIVE_PREFIXES)
