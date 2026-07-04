"""i18n ru/en фронтенда — каталог UI-строк + синхрон локали с языком агента (§23.8).

§23.8 требует локализацию фронтенда: переключатель локали `ru|en`, все
UI-строки через словарь (не хардкод в JSX), выбор локали персистится в
`me/settings` (§14.15) и синхронизируется с языком ответов агента
(`state['language']` ∈ {ru, en}, §7.3 / §13.17).

Этот роутер — единый **источник истины** UI-словаря на бэкенде. Тот же принцип,
что и `answer_localization.LABELS` (§13.17) для шести вкладок ответа, но масштаб —
весь shell: навигация (§17.5), восемь экранов §5.2, кнопки, вкладки, ошибки,
empty-states. Фронт грузит каталог с фолбэком на `en` и рендерит строки по
ключу — так исключается хардкод и обеспечивается полнота (CI-gate §23.8).

Endpoints (все под ``/api/v1/i18n``):

* ``GET  /locales``       — список поддерживаемых локалей (code / native / agent language);
* ``GET  /catalog``       — плоский словарь ``key → string`` для локали (фолбэк на en);
* ``GET  /completeness``  — покрытие переводов и список отсутствующих ключей (i18n-gate);
* ``GET  /me/locale``     — текущая локаль пользователя из ``me/settings``;
* ``PUT  /me/locale``     — сменить локаль: пишет и ``ui_locale``, и ``language``
  (язык ответов агента) — то есть переключатель UI управляет и языком ответа.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api_gateway.auth import current_user
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/i18n", tags=["i18n"])

# Локаль по умолчанию / фолбэк, если у ключа нет перевода для запрошенной локали.
DEFAULT_LOCALE = "ru"
FALLBACK_LOCALE = "en"

# Поддерживаемые локали. ``agent_language`` — код, который уходит в agent-state
# (§7.3): переключатель UI меняет и его, отсюда синхрон языка ответов (§13.17).
LOCALES: list[dict[str, str]] = [
    {"code": "ru", "native": "Русский", "english": "Russian", "agent_language": "ru"},
    {"code": "en", "native": "English", "english": "English", "agent_language": "en"},
]
_LOCALE_CODES = {loc["code"] for loc in LOCALES}

# --------------------------------------------------------------------------
# UI-каталог: ключ → {locale: строка}. Ключи сгруппированы по префиксу
# (``nav.*`` / ``screen.*`` / ``action.*`` / ``tab.*`` / ``state.*`` / ``error.*``
# / ``format.*``), что покрывает навигацию (§17.5), восемь экранов §5.2,
# кнопки, вкладки ответа (§13.17), empty-states и ошибки (§14.2).
# Каждый ключ ОБЯЗАН иметь и ru, и en — иначе падает /completeness (CI-gate).
# --------------------------------------------------------------------------
CATALOG: dict[str, dict[str, str]] = {
    # -- App shell / навигация (§17.5) -------------------------------------
    "app.title": {"ru": "Клубок знаний", "en": "Knowledge Tangle"},
    "app.subtitle": {"ru": "Горное дело · граф знаний", "en": "Mining · knowledge graph"},
    "nav.overview": {"ru": "Обзор", "en": "Overview"},
    "nav.qa": {"ru": "Вопросы и ответы", "en": "Questions & Answers"},
    "nav.gaps": {"ru": "Пробелы и риски", "en": "Gaps & Risks"},
    "nav.knowledge": {"ru": "Знания", "en": "Knowledge"},
    "nav.graph": {"ru": "Граф", "en": "Graph"},
    "nav.evidence": {"ru": "Доказательства", "en": "Evidence"},
    "nav.data": {"ru": "Данные", "en": "Data"},
    "nav.quality": {"ru": "Качество", "en": "Quality"},
    "nav.curation": {"ru": "Курирование", "en": "Curation"},
    "nav.agent": {"ru": "Агент", "en": "Agent"},
    "nav.admin": {"ru": "Администрирование", "en": "Admin"},
    # -- Восемь экранов §5.2 ------------------------------------------------
    "screen.dashboard": {"ru": "Обзор базы знаний", "en": "Knowledge base overview"},
    "screen.chat": {"ru": "Диалог с клубком", "en": "Chat with the tangle"},
    "screen.ask": {"ru": "Запрос к графу", "en": "Graph query"},
    "screen.compare": {"ru": "Сравнение технологий", "en": "Technology comparison"},
    "screen.gaps": {"ru": "Пробелы и риски", "en": "Gaps and risks"},
    "screen.coverage": {"ru": "Покрытие по доменам", "en": "Domain coverage"},
    "screen.entities": {"ru": "Сущности (детали)", "en": "Entities (details)"},
    "screen.documents": {"ru": "Документы", "en": "Documents"},
    "screen.settings": {"ru": "Настройки", "en": "Settings"},
    # -- Кнопки / действия --------------------------------------------------
    "action.send": {"ru": "Отправить", "en": "Send"},
    "action.search": {"ru": "Искать", "en": "Search"},
    "action.reset": {"ru": "Сбросить", "en": "Reset"},
    "action.apply": {"ru": "Применить", "en": "Apply"},
    "action.cancel": {"ru": "Отмена", "en": "Cancel"},
    "action.save": {"ru": "Сохранить", "en": "Save"},
    "action.export": {"ru": "Экспорт", "en": "Export"},
    "action.retry": {"ru": "Повторить", "en": "Retry"},
    "action.expand": {"ru": "Развернуть", "en": "Expand"},
    "action.collapse": {"ru": "Свернуть", "en": "Collapse"},
    "action.copy": {"ru": "Копировать", "en": "Copy"},
    # -- Вкладки ответа (§13.17, синхрон с answer_localization) -------------
    "tab.summary": {"ru": "Сводка", "en": "Summary"},
    "tab.experiments": {"ru": "Эксперименты", "en": "Experiments"},
    "tab.evidence": {"ru": "Доказательства", "en": "Evidence"},
    "tab.graph": {"ru": "Граф", "en": "Graph"},
    "tab.gaps": {"ru": "Пробелы", "en": "Gaps"},
    "tab.contradictions": {"ru": "Противоречия", "en": "Contradictions"},
    # -- Empty-states -------------------------------------------------------
    "state.loading": {"ru": "Загрузка…", "en": "Loading…"},
    "state.empty": {"ru": "Ничего не найдено", "en": "Nothing found"},
    "state.no_results": {"ru": "Нет результатов по запросу", "en": "No results for your query"},
    "state.no_data": {"ru": "Данные отсутствуют", "en": "No data available"},
    "state.select_prompt": {"ru": "Выберите элемент слева", "en": "Select an item on the left"},
    # -- Ошибки (§14.2) -----------------------------------------------------
    "error.generic": {"ru": "Что-то пошло не так", "en": "Something went wrong"},
    "error.network": {"ru": "Ошибка сети", "en": "Network error"},
    "error.not_found": {"ru": "Не найдено", "en": "Not found"},
    "error.unauthorized": {"ru": "Требуется авторизация", "en": "Authorization required"},
    "error.validation": {"ru": "Неверные данные запроса", "en": "Invalid request data"},
    # -- Локализуемые подписи форматирования (§23.8 Intl) -------------------
    "format.number_example_label": {"ru": "Число", "en": "Number"},
    "format.date_example_label": {"ru": "Дата", "en": "Date"},
    "format.unit_temperature": {"ru": "°C", "en": "°C"},
    "format.locale_switcher": {"ru": "Язык интерфейса", "en": "Interface language"},
    "format.sync_note": {
        "ru": "Язык интерфейса синхронизирован с языком ответов агента",
        "en": "Interface language is synced with the agent answer language",
    },
}


class LocaleBody(BaseModel):
    """PUT /me/locale — желаемая локаль UI (она же язык ответов агента)."""

    locale: str


def _resolve(locale: str) -> str:
    """Проверить/нормализовать код локали, иначе 400."""
    code = (locale or "").strip().lower()
    if code not in _LOCALE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported locale '{locale}', expected one of {sorted(_LOCALE_CODES)}",
        )
    return code


def _agent_language(locale: str) -> str:
    """Код языка агента (§7.3) для локали UI — синхрон переключателя и ответа."""
    for loc in LOCALES:
        if loc["code"] == locale:
            return loc["agent_language"]
    return FALLBACK_LOCALE


def _views():  # type: ignore[no-untyped-def]
    """Тот же ViewStore, что и routers/views.py — settings в SQLite (§14.15)."""
    from kg_common.storage.saved_views import ViewStore

    vs = ViewStore(f"sqlite:///{get_settings().runtime_dir}/views.db")
    vs.migrate()
    return vs


@router.get("/locales")
def list_locales() -> dict:
    """Поддерживаемые локали + локаль по умолчанию (для инициализации фронта)."""
    return {"default": DEFAULT_LOCALE, "fallback": FALLBACK_LOCALE, "locales": LOCALES}


@router.get("/catalog")
def get_catalog(locale: str = Query(default=DEFAULT_LOCALE)) -> dict:
    """Плоский словарь ``key → string`` для локали, с фолбэком на ``en`` (§23.8).

    Отсутствующий у ключа перевод подменяется fallback-строкой и попадает в
    ``fallback_keys`` — фронт получает связный каталог без «дыр», а список
    подмен полезен для диагностики полноты.
    """
    code = _resolve(locale)
    messages: dict[str, str] = {}
    fallback_keys: list[str] = []
    for key, translations in CATALOG.items():
        if code in translations:
            messages[key] = translations[code]
        else:
            messages[key] = translations.get(FALLBACK_LOCALE, key)
            fallback_keys.append(key)
    return {
        "locale": code,
        "agent_language": _agent_language(code),
        "count": len(messages),
        "fallback_keys": fallback_keys,
        "messages": messages,
    }


@router.get("/completeness")
def completeness() -> dict:
    """Полнота переводов по всем локалям — источник для i18n-gate CI (§23.8).

    Для каждой локали считает покрытие и перечисляет ключи без перевода.
    ``ok`` истинно, только если каждая локаль покрывает 100% ключей — именно
    это проверяет CI-gate (падает при отсутствующем ключе).
    """
    total = len(CATALOG)
    per_locale: dict[str, Any] = {}
    all_ok = True
    for loc in LOCALES:
        code = loc["code"]
        missing = [k for k, tr in CATALOG.items() if code not in tr or not tr[code].strip()]
        covered = total - len(missing)
        ok = not missing
        all_ok = all_ok and ok
        per_locale[code] = {
            "total": total,
            "covered": covered,
            "missing_count": len(missing),
            "coverage": round(covered / total, 4) if total else 1.0,
            "missing_keys": missing,
            "ok": ok,
        }
    return {"ok": all_ok, "total_keys": total, "locales": per_locale}


@router.get("/me/locale")
def get_my_locale(user: str = Depends(current_user)) -> dict:
    """Текущая локаль пользователя из ``me/settings`` (или дефолт)."""
    settings = _views().get_settings(user) or {}
    code = settings.get("ui_locale") or DEFAULT_LOCALE
    if code not in _LOCALE_CODES:
        code = DEFAULT_LOCALE
    return {
        "user": user,
        "locale": code,
        "agent_language": _agent_language(code),
        "language": settings.get("language") or _agent_language(code),
    }


@router.put("/me/locale")
def set_my_locale(body: LocaleBody, user: str = Depends(current_user)) -> dict:
    """Сменить локаль UI и **синхронно** язык ответов агента (§23.8 / §7.3).

    Пишет в ``me/settings`` сразу два поля — ``ui_locale`` (локаль интерфейса) и
    ``language`` (язык, на котором отвечает агент, §13.17) — одним и тем же
    кодом. Так переключатель локали управляет и языком ответа; значение
    персистится в настройках пользователя (критерий приёмки §23.8).
    """
    code = _resolve(body.locale)
    lang = _agent_language(code)
    store = _views()
    settings = dict(store.get_settings(user) or {})
    settings["ui_locale"] = code
    settings["language"] = lang
    store.set_settings(user, settings)
    return {"user": user, "locale": code, "agent_language": lang, "language": lang}
