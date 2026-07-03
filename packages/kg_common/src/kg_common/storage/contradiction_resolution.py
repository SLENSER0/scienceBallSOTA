"""Contradiction-resolution planner (§16.6).

Чистый планировщик (без стора): вычисляет переход состояния, когда куратор
разрешает задачу типа ``contradiction``, выбирая победившее утверждение. Модуль
не мутирует хранилище — его результат применяет ``CurationService.resolve_contradiction``.

Разрешение противоречия помечает узел ``status="resolved"`` с ссылкой на
победителя (``resolution``) и причиной (``reason``), фиксирует все прочие
утверждения как проигравшие и перечисляет id всех рёбер ``CONTRADICTS``,
подлежащих гашению (quench).

RU/EN: противоречие / contradiction, победитель / winner, гашение / quench.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ResolutionPlan:
    """План разрешения противоречия (§16.6).

    ``node_patch`` — патч узла-противоречия (``status``/``resolution``/``reason``).
    ``loser_claim_ids`` — все утверждения кроме победителя (порядок сохранён).
    ``edges_to_quench`` — id рёбер ``CONTRADICTS``, подлежащих гашению.
    """

    contradiction_id: str
    winner_claim_id: str
    loser_claim_ids: tuple[str, ...]
    node_patch: Mapping[str, Any]
    edges_to_quench: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога)."""
        return asdict(self)


def plan_resolution(
    contradiction: Mapping[str, Any],
    *,
    winner_claim_id: str,
    reason: str = "",
) -> ResolutionPlan:
    """Построить план разрешения противоречия (стор не мутируется).

    ``contradiction`` — ``{id, claim_ids:[...], contradicts_edges:[...]}``.
    Победитель должен присутствовать в ``claim_ids``, иначе :class:`KeyError`.
    Прочие ``claim_ids`` становятся проигравшими; ``node_patch`` фиксирует
    ``status="resolved"``, ``resolution=winner_claim_id`` и ``reason``.
    """
    contradiction_id = contradiction["id"]
    claim_ids = list(contradiction.get("claim_ids", []))
    if winner_claim_id not in claim_ids:
        raise KeyError(
            f"winner {winner_claim_id!r} not among claim_ids of contradiction {contradiction_id!r}"
        )
    losers = tuple(c for c in claim_ids if c != winner_claim_id)
    edges = tuple(contradiction.get("contradicts_edges", []))
    node_patch: dict[str, Any] = {
        "status": "resolved",
        "resolution": winner_claim_id,
        "reason": reason,
    }
    return ResolutionPlan(
        contradiction_id=contradiction_id,
        winner_claim_id=winner_claim_id,
        loser_claim_ids=losers,
        node_patch=node_patch,
        edges_to_quench=edges,
    )
