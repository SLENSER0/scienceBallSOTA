"""MERGE ON CREATE / ON MATCH field-partition policy (§3.8, §3.7).

Шаблоны ``MERGE`` должны декларативно разделять поля узла на три класса:
*immutable* (только ``ON CREATE``), *updatable* (``ON MATCH``) и
*reviewed/protected* (проверенные фактические слоты, которые нельзя молча
перезаписывать). Существующий ``verified_field_guard`` умеет фильтровать набор
проверенных полей, но нигде не объявлен сам раздел create-only/protected — этот
модуль (*module*) закрывает пробел (§3.8).

Константы (*constants*):

* :data:`CREATE_ONLY_FIELDS` — поля идентичности/происхождения, которые пишутся
  один раз при создании и никогда не обновляются (``id``, ``created_at``,
  ``created_by``).
* :data:`PROTECTED_FIELDS` — рецензируемые фактические слоты (``value``,
  ``value_normalized``, ``effect_direction``, ``review_status``): их можно
  обновлять по ``ON MATCH`` только пока запись не принята рецензентом.

Замороженный датакласс (*frozen dataclass*) :class:`MergePolicy` связывает метку
с её разделами и сериализуется через :meth:`MergePolicy.as_dict`.

Функции (*functions*):

* :func:`policy_for` — вернуть :class:`MergePolicy` для метки узла.
* :func:`is_protected` — ``True`` тогда и только тогда, когда поле входит в
  :data:`PROTECTED_FIELDS` и ``review_status`` уже подтверждён
  (``accepted`` / ``corrected``).
* :func:`split_on_match` — из входящего словаря убрать все create-only поля и все
  защищённые поля (при подтверждённом статусе), оставив только то, что безопасно
  писать по ``ON MATCH``.

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их
читают через ``get_node()``; политика оперирует именами полей, а не колонками
хранилища, и потому одинаково применима к базовым и кастомным свойствам.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Поля идентичности/происхождения: пишутся один раз при создании (§3.8).
CREATE_ONLY_FIELDS: tuple[str, ...] = ("id", "created_at", "created_by")

# Рецензируемые фактические слоты: защищаются после подтверждения (§3.8/§3.7).
PROTECTED_FIELDS: tuple[str, ...] = (
    "value",
    "value_normalized",
    "effect_direction",
    "review_status",
)

# Статусы рецензии, при которых защищённое поле нельзя молча перезаписывать.
_CONFIRMED_REVIEW_STATUSES: frozenset[str] = frozenset({"accepted", "corrected"})


@dataclass(frozen=True)
class MergePolicy:
    """Immutable create-only / protected field partition for a node label (§3.8).

    Attributes
    ----------
    label:
        Метка узла (*node label*), к которой применяется политика (e.g.
        ``"Measurement"``).
    create_only:
        Поля, записываемые только при создании (``ON CREATE``) и никогда не
        обновляемые по ``ON MATCH``.
    protected:
        Рецензируемые фактические слоты, обновляемые по ``ON MATCH`` лишь пока
        запись не подтверждена рецензентом.
    """

    label: str
    create_only: tuple[str, ...]
    protected: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.8)."""
        return {
            "label": self.label,
            "create_only": list(self.create_only),
            "protected": list(self.protected),
        }


def policy_for(label: str) -> MergePolicy:
    """Return the :class:`MergePolicy` for ``label`` (§3.8).

    Раздел одинаков для всех меток: create-only поля берутся из
    :data:`CREATE_ONLY_FIELDS`, защищённые — из :data:`PROTECTED_FIELDS`. Метка
    сохраняется в политике, чтобы шаблон ``MERGE`` мог сослаться на источник.
    """
    return MergePolicy(
        label=label,
        create_only=CREATE_ONLY_FIELDS,
        protected=PROTECTED_FIELDS,
    )


def is_protected(field: str, review_status: str) -> bool:
    """Return ``True`` iff ``field`` is a confirmed protected slot (§3.8/§3.7).

    Защита включается только когда поле входит в :data:`PROTECTED_FIELDS` и
    ``review_status`` уже подтверждён (``accepted`` / ``corrected``). Для
    ``pending`` и прочих статусов защищённое поле ещё можно обновлять.
    """
    return field in PROTECTED_FIELDS and review_status in _CONFIRMED_REVIEW_STATUSES


def split_on_match(label: str, incoming: Mapping[str, Any], review_status: str) -> dict[str, Any]:
    """Return the subset of ``incoming`` safe to write via ``ON MATCH`` (§3.8).

    Из входящего словаря удаляются:

    * все create-only поля (:data:`CREATE_ONLY_FIELDS`) — их пишут лишь при
      создании;
    * все защищённые поля при подтверждённом ``review_status`` (см.
      :func:`is_protected`).

    Остальные ключи (``unit``, ``updated_at`` и т.п.) сохраняются как есть.
    ``label`` учитывается через :func:`policy_for`, что оставляет задел под
    метка-специфичные разделы в будущем.
    """
    policy = policy_for(label)
    create_only = set(policy.create_only)
    return {
        key: val
        for key, val in incoming.items()
        if key not in create_only and not is_protected(key, review_status)
    }


__all__ = [
    "CREATE_ONLY_FIELDS",
    "PROTECTED_FIELDS",
    "MergePolicy",
    "policy_for",
    "is_protected",
    "split_on_match",
]
