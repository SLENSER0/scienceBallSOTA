"""RFC 5988 ``Link`` header builder for list endpoints (§14.2).

Пагинация через заголовок ``Link``: по ``offset``/``limit``/``total`` вычисляются
ссылки ``first``/``prev``/``next``/``last`` и рендерятся в формат RFC 5988
``<url>; rel="name"`` (через запятую). ``prev`` — ``None`` на первой странице,
``next`` — ``None`` на последней, а смещение ``last`` — наибольшее кратное
``limit``, строго меньшее ``total``.

RFC 5988 ``Link`` header pagination. From ``offset``/``limit``/``total`` we derive
``first``/``prev``/``next``/``last`` URLs and render them as comma-joined
``<url>; rel="name"`` entries. ``prev`` is ``None`` on the first page, ``next`` is
``None`` on the last, and the ``last`` offset is the largest multiple of ``limit``
strictly below ``total``.

* :class:`LinkSet` — frozen four-relation set with :meth:`as_dict`.
* :func:`build_links` — offset/limit/total → :class:`LinkSet` of ``?offset=&limit=`` URLs.
* :func:`render` — :class:`LinkSet` → RFC 5988 header string (non-``None`` rels only).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LinkSet:
    """Неизменяемый набор ссылок пагинации / immutable pagination links (§14.2).

    Each field is either a fully-formed ``?offset=&limit=`` URL or ``None`` when
    the relation does not apply (``prev`` on the first page, ``next`` on the last).
    """

    first: str | None
    prev: str | None
    next: str | None
    last: str | None

    def as_dict(self) -> dict[str, str | None]:
        """Структурное представление набора ссылок / wire mapping (§14.2)."""
        return {
            "first": self.first,
            "prev": self.prev,
            "next": self.next,
            "last": self.last,
        }


def _url(path: str, offset: int, limit: int) -> str:
    """Собрать URL страницы ``<path>?offset=&limit=`` / page URL (§14.2)."""
    return f"{path}?offset={offset}&limit={limit}"


def build_links(path: str, offset: int, limit: int, total: int) -> LinkSet:
    """Вычислить ссылки ``first``/``prev``/``next``/``last`` (§14.2).

    ``first`` всегда указывает на ``offset=0``. ``prev`` — ``None`` на первой
    странице (``offset <= 0``), иначе ``max(0, offset - limit)``. ``next`` —
    ``None``, когда ``offset + limit >= total`` (последняя страница), иначе
    ``offset + limit``. Смещение ``last`` — наибольшее кратное ``limit``, строго
    меньшее ``total`` (``0`` при пустой выборке). ``limit`` обязан быть
    положительным.
    """
    if limit <= 0:
        raise ValueError("limit must be >= 1")

    first = _url(path, 0, limit)

    prev = None if offset <= 0 else _url(path, max(0, offset - limit), limit)

    next_offset = offset + limit
    nxt = None if next_offset >= total else _url(path, next_offset, limit)

    last_offset = ((total - 1) // limit) * limit if total > 0 else 0
    last = _url(path, last_offset, limit)

    return LinkSet(first=first, prev=prev, next=nxt, last=last)


def render(links: LinkSet) -> str:
    """Отрендерить набор ссылок в заголовок RFC 5988 ``Link`` (§14.2).

    Emits one ``<url>; rel="name"`` entry per non-``None`` relation, in the order
    ``first, prev, next, last``, joined by ``", "``. An all-``None`` set renders
    to the empty string.
    """
    parts: list[str] = []
    for rel, url in (
        ("first", links.first),
        ("prev", links.prev),
        ("next", links.next),
        ("last", links.last),
    ):
        if url is not None:
            parts.append(f'<{url}>; rel="{rel}"')
    return ", ".join(parts)
