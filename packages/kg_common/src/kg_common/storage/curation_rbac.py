"""RBAC-роли curation (§16.9): viewer / curator / admin и их права на действия.

Курирование графа (accept/reject/correct/merge/…) выполняется под одной из трёх
ролей. Модуль — чистый Python без стора: он держит статические карты «роль →
множество разрешённых действий» и функцию :func:`can`, которая выдаёт решение
доступа (:class:`AccessDecision`) с HTTP-подобным статусом.

Иерархия:

* ``viewer`` — только чтение (``read``); никаких мутирующих действий.
* ``curator`` — приёмка/правка предложений: accept, reject, correct, alias_add,
  mark_inferred, manual_evidence, annotate_gap, mark_verified, resolve.
* ``admin`` — всё, что может curator, плюс структурные операции: merge, split,
  schema_change, revert, assign.

Статусы (HTTP-подобные):

* ``200`` — действие разрешено роли (allowed=True);
* ``403`` — роль известна, но действия ей не хватает (allowed=False);
* ``401`` — роль пуста/анонимна (allowed=False).

RU/EN: роль / role, действие / action, разрешено / allowed, запрещено /
forbidden, неавторизован / unauthorized, наблюдатель / viewer, куратор /
curator, администратор / admin.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# --- HTTP-подобные статусы решения / decision statuses --------------------
STATUS_OK = 200  # разрешено / allowed
STATUS_FORBIDDEN = 403  # роль есть, прав нет / known role, missing right
STATUS_UNAUTHORIZED = 401  # анонимно/пусто / anonymous or empty role

# --- Действие «только чтение» / read-only action --------------------------
READ_ACTION = "read"

# viewer: только чтение / read-only.
VIEWER_ACTIONS: frozenset[str] = frozenset({READ_ACTION})

# curator: приёмка и правка предложений / accept & correct proposals.
CURATOR_ACTIONS: frozenset[str] = VIEWER_ACTIONS | frozenset(
    {
        "accept",
        "reject",
        "correct",
        "alias_add",
        "mark_inferred",
        "manual_evidence",
        "annotate_gap",
        "mark_verified",
        "resolve",
    }
)

# admin: всё curator + структурные операции / plus structural ops.
ADMIN_ACTIONS: frozenset[str] = CURATOR_ACTIONS | frozenset(
    {
        "merge",
        "split",
        "schema_change",
        "revert",
        "assign",
    }
)

# Карта «роль → множество действий» / role → allowed actions.
ROLE_ACTIONS: dict[str, frozenset[str]] = {
    "viewer": VIEWER_ACTIONS,
    "curator": CURATOR_ACTIONS,
    "admin": ADMIN_ACTIONS,
}


@dataclass(frozen=True)
class AccessDecision:
    """Решение доступа для пары (роль, действие) (§16.9).

    `allowed` — разрешено ли действие; `status` — HTTP-подобный статус
    (200/403/401); `role` — нормализованная роль (эхо входа); `action` —
    запрошенное действие (эхо входа).
    """

    allowed: bool
    status: int
    role: str
    action: str

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога); `action` эхо-ит вход."""
        return asdict(self)


def allowed_actions(role: str) -> set[str]:
    """Множество разрешённых действий для роли (пустое для неизвестной/пустой)."""
    normalized = (role or "").strip().lower()
    return set(ROLE_ACTIONS.get(normalized, frozenset()))


def can(role: str, action: str) -> AccessDecision:
    """Решить, может ли `role` выполнить `action` (§16.9).

    401 — если роль пуста/анонимна; 200 — если действие входит в набор роли;
    403 — если роль известна, но действия ей не хватает (или роль неизвестна).
    """
    normalized = (role or "").strip().lower()
    if not normalized:
        return AccessDecision(allowed=False, status=STATUS_UNAUTHORIZED, role="", action=action)
    actions = ROLE_ACTIONS.get(normalized, frozenset())
    if action in actions:
        return AccessDecision(allowed=True, status=STATUS_OK, role=normalized, action=action)
    return AccessDecision(allowed=False, status=STATUS_FORBIDDEN, role=normalized, action=action)
