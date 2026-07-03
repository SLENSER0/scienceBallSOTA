"""UI-настройки пользователя: валидация и слияние с дефолтами (§14.15).

Проверяет и сливает полезную нагрузку UI-настроек для ``PUT /me/settings``.
Хранилище :mod:`kg_common.storage.saved_views` сохраняет сырой JSON-блоб, но
не выполняет никакой проверки ключей/значений и не подставляет умолчания —
эта логика вынесена сюда, чтобы её было легко тестировать и переиспользовать.

Validate and merge the UI-settings payload for ``PUT /me/settings``.
``kg_common.storage.saved_views`` persists a raw JSON blob but performs no
key/value validation or defaulting; that logic lives here so it stays hermetic
and easy to unit-test.

* :data:`ALLOWED_SETTING_KEYS` — белый список ключей / permitted keys.
* :data:`ALLOWED_LOCALES`      — допустимые локали / permitted locales.
* :data:`DEFAULT_SETTINGS`     — значения по умолчанию / defaults.
* :class:`UserSettings`        — неизменяемый снимок настроек с :meth:`as_dict`.
* :func:`validate_settings`    — проверка патча (raises ``ValueError``).
* :func:`merge_settings`       — дефолты ← current ← валидированный патч.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Разрешённые ключи настроек / permitted setting keys.
ALLOWED_SETTING_KEYS: frozenset[str] = frozenset(
    {"theme", "locale", "page_size", "default_layout", "graph_mode"}
)

#: Допустимые локали интерфейса / permitted UI locales.
ALLOWED_LOCALES: frozenset[str] = frozenset({"en", "ru"})

#: Минимальный и максимальный размер страницы / page-size bounds (inclusive).
_PAGE_SIZE_MIN = 1
_PAGE_SIZE_MAX = 200

#: Значения по умолчанию для всех ключей / defaults for every key.
DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "system",
    "locale": "en",
    "page_size": 25,
    "default_layout": "list",
    "graph_mode": "2d",
}


@dataclass(frozen=True, slots=True)
class UserSettings:
    """Неизменяемый снимок UI-настроек пользователя (§14.15).

    Immutable snapshot of a user's UI settings. ``values`` is the fully merged
    mapping (defaults overlaid by stored settings and the validated patch).
    """

    values: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление настроек / wire form (§14.15)."""
        return dict(self.values)


def validate_settings(patch: Mapping[str, Any]) -> dict[str, Any]:
    """Проверить патч настроек и вернуть его копию (§14.15).

    Проверяет каждый ключ по :data:`ALLOWED_SETTING_KEYS`, локаль по
    :data:`ALLOWED_LOCALES` и ``page_size`` в пределах ``1..200``. Возвращает
    неглубокую копию входа (сам патч не мутируется).

    Validate a settings patch and return a shallow copy. Every key must be in
    :data:`ALLOWED_SETTING_KEYS`, ``locale`` (if present) must be in
    :data:`ALLOWED_LOCALES`, and ``page_size`` (if present) must be an ``int``
    within ``1..200`` inclusive.

    :raises ValueError: неизвестный ключ, недопустимая локаль или ``page_size``
        вне диапазона / unknown key, bad locale or out-of-range ``page_size``.
    """
    validated: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in ALLOWED_SETTING_KEYS:
            raise ValueError(f"unknown setting key: {key!r}")
        if key == "locale" and value not in ALLOWED_LOCALES:
            raise ValueError(f"unsupported locale: {value!r}")
        if key == "page_size":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"page_size must be an int: {value!r}")
            if not (_PAGE_SIZE_MIN <= value <= _PAGE_SIZE_MAX):
                raise ValueError(f"page_size out of range 1..200: {value!r}")
        validated[key] = value
    return validated


def merge_settings(current: Mapping[str, Any], patch: Mapping[str, Any]) -> UserSettings:
    """Слить дефолты, текущие настройки и валидированный патч (§14.15).

    Порядок наложения: :data:`DEFAULT_SETTINGS` перекрываются ``current``, затем
    провалидированным ``patch``. Патч проверяется через :func:`validate_settings`,
    поэтому недопустимые ключи/значения приводят к ``ValueError``.

    Overlay order: :data:`DEFAULT_SETTINGS` overlaid by ``current`` then by the
    validated ``patch``. The patch is checked via :func:`validate_settings`, so
    bad keys/values raise ``ValueError``.
    """
    merged: dict[str, Any] = dict(DEFAULT_SETTINGS)
    merged.update(current)
    merged.update(validate_settings(patch))
    return UserSettings(values=merged)
