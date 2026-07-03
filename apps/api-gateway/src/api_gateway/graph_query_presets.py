"""Left-sidebar graph query template preset registry (§17.8).

Проводник графа (§17.8) показывает слева готовые шаблоны запросов с формой
параметров, но до сих пор существовал лишь :mod:`graph_query_body`, который
только парсит и валидирует уже присланное тело — каталога пресетов не было.
Модуль на чистом stdlib даёт неизменяемый реестр шаблонов: каждое поле формы
описано схемой (имя, тип, обязательность, значение по умолчанию), а
:func:`build_request` собирает из значений формы тело в форме
:class:`~api_gateway.graph_query_body.GraphQueryBody` (``query_type``,
``material``, вложенный ``processing``, ``property``).

The §17.8 Graph Explorer renders ready-made query templates with a parameter
form in the left sidebar, yet only :mod:`graph_query_body` existed — it merely
parses/validates a submitted body, with no preset catalog. Pure standard
library:

* :class:`PresetField` — frozen ``{name, type, required, default}`` form field.
* :class:`QueryPreset` — frozen template ``{key, title, query_type,
  description, fields}`` with :meth:`as_dict`.
* :func:`list_presets` / :func:`get_preset` — registry access.
* :func:`build_request` — map form values into a GraphQueryBody-shaped request,
  applying field defaults and raising on a missing required field.
"""

from __future__ import annotations

from dataclasses import dataclass

# Поля формы, попадающие во вложенный ``processing`` §6.2 / §6.2 processing
# sub-fields; all other fields land at the top level of the request body.
_PROCESSING_FIELDS: frozenset[str] = frozenset({"operation", "temperature_c", "time_h"})


@dataclass(frozen=True)
class PresetField:
    """Неизменяемое описание поля формы параметров §17.8 / frozen §17.8 field.

    ``name`` — имя параметра; ``type`` — тип виджета формы (``'string'``,
    ``'number'`` …); ``required`` — обязательность; ``default`` — значение по
    умолчанию или ``None``. :meth:`as_dict` даёт плоский вид для UI и проверок.

    Describes one parameter form control: its ``name``, form ``type``, whether
    it is ``required``, and a ``default`` value (or ``None``).
    """

    name: str
    type: str
    required: bool
    default: object | None

    def as_dict(self) -> dict[str, object | None]:
        """Плоский dict поля формы / plain field dict for the UI and asserts."""
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
        }


@dataclass(frozen=True)
class QueryPreset:
    """Неизменяемый шаблон графового запроса §17.8 / frozen §17.8 query preset.

    ``key`` — стабильный идентификатор пресета; ``title`` — подпись в сайдбаре;
    ``query_type`` — тип запроса §6.2/§14.6; ``description`` — пояснение;
    ``fields`` — кортеж :class:`PresetField`, описывающий форму параметров.

    Immutable sidebar template: a stable ``key``, a human ``title``, the §6.2
    ``query_type`` it builds, a ``description``, and the ordered ``fields`` of
    its parameter form.
    """

    key: str
    title: str
    query_type: str
    description: str
    fields: tuple[PresetField, ...]

    def as_dict(self) -> dict[str, object]:
        """Dict пресета с полями-схемами / preset dict with field schemas."""
        return {
            "key": self.key,
            "title": self.title,
            "query_type": self.query_type,
            "description": self.description,
            "fields": tuple(field.as_dict() for field in self.fields),
        }


# Реестр шаблонов сайдбара §17.8 / the §17.8 sidebar template registry.
_PRESETS: tuple[QueryPreset, ...] = (
    QueryPreset(
        key="material_regime_property",
        title="Material · regime → property",
        query_type="material_regime_property",
        description=(
            "Свойство материала при заданном режиме обработки / a material's "
            "property under a given processing regime."
        ),
        fields=(
            PresetField("material", "string", True, None),
            PresetField("operation", "string", False, "aging"),
            PresetField("temperature_c", "number", False, None),
            PresetField("property", "string", False, None),
        ),
    ),
    QueryPreset(
        key="property_material",
        title="Property → materials",
        query_type="property_material",
        description=(
            "Материалы, обладающие заданным свойством / materials that exhibit a given property."
        ),
        fields=(PresetField("property", "string", True, None),),
    ),
)


def list_presets() -> tuple[QueryPreset, ...]:
    """Все шаблоны сайдбара §17.8 / every §17.8 sidebar preset, in order."""
    return _PRESETS


def get_preset(key: str) -> QueryPreset | None:
    """Пресет по ключу или ``None`` / preset by key, or ``None`` if unknown."""
    for preset in _PRESETS:
        if preset.key == key:
            return preset
    return None


def build_request(key: str, values: dict[str, object]) -> dict[str, object]:
    """Собрать тело запроса §6.2 из значений формы §17.8 / build a §6.2 body.

    Значения формы раскладываются в форму
    :class:`~api_gateway.graph_query_body.GraphQueryBody`: ``operation`` и
    ``temperature_c`` идут во вложенный ``processing``, остальные (``material``,
    ``property``) — на верхний уровень. Отсутствующее поле берёт свой
    ``default``; обязательное поле без значения и без умолчания — ошибка.

    Maps form ``values`` into a GraphQueryBody-shaped request. ``operation`` /
    ``temperature_c`` go into a nested ``processing`` block, the rest stay at the
    top level. A missing field falls back to its ``default``; a required field
    with neither a supplied value nor a default raises :class:`ValueError`.
    """
    preset = get_preset(key)
    if preset is None:
        raise ValueError(f"unknown preset: {key!r}")

    request: dict[str, object] = {"query_type": preset.query_type}
    processing: dict[str, object] = {}
    for field in preset.fields:
        if field.name in values:
            value = values[field.name]
        elif field.default is not None:
            value = field.default
        elif field.required:
            raise ValueError(f"missing required field {field.name!r} for preset {key!r}")
        else:
            continue
        if field.name in _PROCESSING_FIELDS:
            processing[field.name] = value
        else:
            request[field.name] = value

    if processing:
        request["processing"] = processing
    return request
