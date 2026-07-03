"""DataHub-style URN builder/parser (§10.3).

RU: Построение и разбор URN в стиле DataHub для датасетов, источников и документов.
EN: Build and parse DataHub-style URNs for datasets, sources and documents.

Dataset form:      ``urn:li:{entity_type}:(urn:li:dataPlatform:{platform},{key},{env})``
Non-dataset form:  ``urn:li:{entity_type}:{key}``
"""

from __future__ import annotations

from dataclasses import dataclass

_URN_PREFIX = "urn:li:"
_PLATFORM_PREFIX = "urn:li:dataPlatform:"
_SOURCE_PLATFORM = "kg-source"
_DOCUMENT_PLATFORM = "kg-document"
_DEFAULT_ENV = "PROD"


@dataclass(frozen=True)
class Urn:
    """Immutable URN value object.

    RU: Неизменяемый объект URN (платформа, тип сущности, ключ, окружение).
    EN: Immutable URN (platform, entity type, key, environment).
    """

    platform: str
    entity_type: str
    key: str
    env: str = _DEFAULT_ENV

    def to_str(self) -> str:
        """RU: Сериализовать в строку URN. EN: Serialize to a URN string."""
        if self.entity_type == "dataset":
            return (
                f"{_URN_PREFIX}{self.entity_type}:"
                f"({_PLATFORM_PREFIX}{self.platform},{self.key},{self.env})"
            )
        return f"{_URN_PREFIX}{self.entity_type}:{self.key}"

    def __str__(self) -> str:
        return self.to_str()

    def as_dict(self) -> dict[str, str]:
        """RU: Представить как словарь. EN: Represent as a plain dict."""
        return {
            "platform": self.platform,
            "entity_type": self.entity_type,
            "key": self.key,
            "env": self.env,
        }


def dataset_urn(platform: str, key: str, env: str = _DEFAULT_ENV) -> str:
    """RU: URN датасета. EN: Build a dataset URN string."""
    return Urn(platform=platform, entity_type="dataset", key=key, env=env).to_str()


def source_urn(source_id: str) -> str:
    """RU: URN источника (платформа ``kg-source``). EN: Source URN (``kg-source``)."""
    return dataset_urn(_SOURCE_PLATFORM, source_id)


def document_urn(doc_id: str) -> str:
    """RU: URN документа (платформа ``kg-document``). EN: Document URN (``kg-document``)."""
    return dataset_urn(_DOCUMENT_PLATFORM, doc_id)


def parse_urn(s: str) -> Urn:
    """RU: Разобрать строку URN обратно в :class:`Urn`.

    EN: Parse a URN string back into a :class:`Urn`. Round-trips ``to_str``.
    Raises :class:`ValueError` for malformed input.
    """
    if not isinstance(s, str) or not s.startswith(_URN_PREFIX):
        raise ValueError(f"not a urn: {s!r}")
    rest = s[len(_URN_PREFIX) :]
    entity_type, sep, remainder = rest.partition(":")
    if not sep or not entity_type or not remainder:
        raise ValueError(f"malformed urn: {s!r}")
    if remainder.startswith("(") and remainder.endswith(")"):
        inner = remainder[1:-1]
        if not inner.startswith(_PLATFORM_PREFIX):
            raise ValueError(f"malformed dataset urn: {s!r}")
        body = inner[len(_PLATFORM_PREFIX) :]
        parts = body.split(",")
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"malformed dataset urn body: {s!r}")
        platform, key, env = parts
        return Urn(platform=platform, entity_type=entity_type, key=key, env=env)
    return Urn(platform="", entity_type=entity_type, key=remainder, env=_DEFAULT_ENV)


def is_valid_urn(s: str) -> bool:
    """RU: Проверить корректность URN. EN: Return True if ``s`` parses as a URN."""
    try:
        parse_urn(s)
    except (ValueError, TypeError):
        return False
    return True
