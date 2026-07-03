"""Readiness/liveness rollup for ``GET /admin/health`` (§14.11).

Свёртка (rollup) агрегирует пер-зависимостные проверки в единый статус
``ok|degraded|down`` с разделением критичных и опциональных зависимостей:
HTTP 503 отдаётся только когда падает критичная зависимость, падение лишь
опциональной даёт ``degraded`` с HTTP 200. Так readiness-пробы не «валят»
сервис из-за некритичной подсистемы.

Aggregates per-dependency checks into a single ``ok|degraded|down`` status
with a critical-vs-optional split: HTTP 503 is returned only when a critical
dependency is down; when only optional dependencies fail the rollup stays at
``degraded`` with HTTP 200. This keeps readiness probes from tearing the
service down over a non-critical subsystem.

* :class:`HealthRollup` — frozen result with :meth:`as_dict`.
* :func:`roll_up`       — ``{name: healthy?}`` (+ critical set) → rollup.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class HealthRollup:
    """Итог свёртки здоровья: статус, пер-проверки, HTTP-код (§14.11).

    * ``status``    — ``"ok"`` / ``"degraded"`` / ``"down"``.
    * ``checks``    — ``{name: "ok"|"down"}`` для каждой зависимости.
    * ``http_code`` — 200, кроме падения критичной зависимости (503).
    """

    status: str
    checks: dict[str, str]
    http_code: int

    def as_dict(self) -> dict[str, object]:
        """Сериализовать в JSON-совместимый словарь / serialize to a dict."""
        return {
            "status": self.status,
            "checks": dict(self.checks),
            "http_code": self.http_code,
        }


def roll_up(checks: Mapping[str, bool], *, critical: set[str]) -> HealthRollup:
    """Свернуть проверки зависимостей в единый статус (§14.11).

    ``checks`` maps each dependency name to a health boolean (``True`` = up).
    ``critical`` names the dependencies whose failure must fail readiness.

    * all ``True`` (or empty) → ``"ok"``, HTTP 200;
    * any critical dependency ``False`` → ``"down"``, HTTP 503 (dominates,
      even if optional dependencies are also down);
    * only optional dependencies ``False`` → ``"degraded"``, HTTP 200.

    The returned ``checks`` map renders each name as ``"ok"`` or ``"down"``.
    """
    rendered = {name: ("ok" if healthy else "down") for name, healthy in checks.items()}

    critical_down = any(not healthy for name, healthy in checks.items() if name in critical)
    any_down = any(not healthy for healthy in checks.values())

    if critical_down:
        return HealthRollup(status="down", checks=rendered, http_code=503)
    if any_down:
        return HealthRollup(status="degraded", checks=rendered, http_code=200)
    return HealthRollup(status="ok", checks=rendered, http_code=200)
