"""Graph render-mode + layout auto-switch selector for §17.8/§17.9 Graph Explorer.

Чистый селектор (pure selector, no DB, no I/O): по числу узлов/рёбер выбирает режим
рендеринга графа и перечисляет допустимые раскладки для каждого режима. Малые графы
рисует Reagraph (§17.8); при достижении порога (``sigma_threshold``, по умолчанию 2000
узлов) авто-переключается на Sigma.js для больших графов (§17.9). Явно запрошенный
корректный режим (``requested``) всегда побеждает авто-правило; некорректный ``requested``
игнорируется, и применяются авто-правила.

Modes / режимы: ``reagraph`` (default, §17.8), ``sigma`` (large-graph WebGL, §17.9),
``cytoscape`` (rich layouts), ``force3d`` (3D force layout). Каждый режим несёт
неизменный кортеж допустимых раскладок в :data:`MODE_LAYOUTS`.

Kuzu note: custom node props are NOT queryable columns — a retriever RETURNs base
columns and reads the rest via ``get_node``; this module counts already-materialised
elements and never touches the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Каталог допустимых раскладок для каждого режима (§17.8/§17.9). Порядок фиксирован —
# первый элемент кортежа считается раскладкой по умолчанию для режима на фронтенде.
MODE_LAYOUTS: dict[str, tuple[str, ...]] = {
    "reagraph": ("forceDirected2d", "radial", "hierarchical", "circular"),
    "sigma": ("forceatlas2", "noverlap", "circular", "random"),
    "cytoscape": ("cose", "concentric", "breadthfirst", "grid", "circle"),
    "force3d": ("forceDirected3d", "sphere", "radialOut"),
}

# Режим по умолчанию для малых графов (§17.8).
DEFAULT_MODE = "reagraph"


@dataclass(frozen=True)
class RenderModeDecision:
    """§17.8/§17.9 решение о режиме рендеринга графа и его допустимых раскладках.

    ``mode`` — выбранный режим (ключ :data:`MODE_LAYOUTS`); ``reason`` — RU/EN причина
    выбора (``default`` / ``threshold`` / ``requested``); ``node_count`` / ``edge_count`` —
    размеры графа, по которым принято решение; ``layouts`` — неизменный кортеж допустимых
    раскладок выбранного режима.
    """

    mode: str
    reason: str
    node_count: int
    edge_count: int
    layouts: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.3 camelCase payload (copies the layouts tuple)."""
        return {
            "mode": self.mode,
            "reason": self.reason,
            "nodeCount": self.node_count,
            "edgeCount": self.edge_count,
            "layouts": list(self.layouts),
        }


def available_layouts(mode: str) -> tuple[str, ...]:
    """Допустимые раскладки для ``mode`` (пустой кортеж для неизвестного режима)."""
    return MODE_LAYOUTS.get(mode, ())


def choose_render_mode(
    node_count: int,
    edge_count: int,
    *,
    requested: str | None = None,
    sigma_threshold: int = 2000,
) -> RenderModeDecision:
    """Выбрать режим рендеринга графа по §17.8/§17.9 из размеров и (опц.) запроса.

    Правила приоритета:

    1. Корректный ``requested`` (ключ :data:`MODE_LAYOUTS`) всегда побеждает — reason
       ``requested``.
    2. Иначе при ``node_count >= sigma_threshold`` — авто-переключение на ``sigma``
       (§17.9), reason содержит ``threshold``.
    3. Иначе режим по умолчанию :data:`DEFAULT_MODE` (``reagraph``, §17.8), reason
       ``default``.

    Некорректный ``requested`` (не ключ :data:`MODE_LAYOUTS`) игнорируется, и применяются
    авто-правила 2–3.
    """
    if requested is not None and requested in MODE_LAYOUTS:
        mode = requested
        reason = f"requested: explicit mode '{requested}' honoured"
    elif node_count >= sigma_threshold:
        mode = "sigma"
        reason = (
            f"threshold: node_count {node_count} >= sigma_threshold {sigma_threshold}, "
            "auto-switch to Sigma.js (§17.9)"
        )
    else:
        mode = DEFAULT_MODE
        reason = f"default: {DEFAULT_MODE} for small graph (§17.8)"
    return RenderModeDecision(
        mode=mode,
        reason=reason,
        node_count=node_count,
        edge_count=edge_count,
        layouts=MODE_LAYOUTS[mode],
    )
