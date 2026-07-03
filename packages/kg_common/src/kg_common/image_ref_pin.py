"""Container image reference pin checker — вендоринг/закрепление версий (§2.12).

Reproducible deployments require that every container image is *pinned* to an
immutable identity — a digest (``@sha256:…``) or at least a concrete, non-floating
tag. A bare ``repo`` or a ``:latest`` tag silently drifts as upstream re-publishes,
so this module parses image references and reports which services are unpinned.
Закрепление версий образов: без дайджеста или конкретного тега сборка «плывёт».

Everything is deterministic and side-effect free — pure parsing and comparison,
no registry calls, no network, no clock.

A reference has the shape ``[registry/]repository[:tag][@sha256:…]``. The registry
is only present when the *first* path segment looks like a host — it contains a
``.`` (``quay.io``) or a ``:`` (``localhost:5000``). Otherwise the whole path is
the repository (``docling-project/docling-serve``), matching Docker's own rule.

Public API:

* :class:`ImageRef`  — frozen ``{registry, repository, tag, digest}`` + ``as_dict``.
* :class:`PinReport` — frozen ``{unpinned, pinned, ok}`` + ``as_dict``.
* :func:`parse_image_ref` — split a reference string into an :class:`ImageRef`.
* :func:`is_pinned`       — True iff a digest is present or the tag is concrete.
* :func:`check_pins`      — roll a ``service -> image`` mapping into a report.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "ImageRef",
    "PinReport",
    "check_pins",
    "is_pinned",
    "parse_image_ref",
]

# The floating tag that must never count as pinned — плавающий тег (§2.12).
_LATEST = "latest"


@dataclass(frozen=True)
class ImageRef:
    """A parsed container image reference — разобранная ссылка на образ (§2.12).

    ``registry`` is the host component (``quay.io``, ``localhost:5000``) or
    ``None`` when the reference uses the default registry. ``repository`` is the
    image path, possibly namespaced (``docling-project/docling-serve``). ``tag``
    is the human tag (``2026.05-community``) or ``None`` when omitted. ``digest``
    is the content-addressable id (``sha256:…``) or ``None``.

    Frozen so a reference can be shared, hashed and serialized safely.
    """

    registry: str | None
    repository: str
    tag: str | None
    digest: str | None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — ``{registry, repository, tag, digest}`` (§2.12)."""
        return {
            "registry": self.registry,
            "repository": self.repository,
            "tag": self.tag,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class PinReport:
    """The pin-audit result over a set of services — отчёт о закреплении (§2.12).

    ``unpinned`` is a tuple of ``(service, image)`` pairs whose references are not
    pinned, in the order the services were supplied. ``pinned`` is the tuple of
    service names that are pinned. ``ok`` is True iff nothing is unpinned.

    Frozen and fully serializable via :meth:`as_dict`.
    """

    unpinned: tuple[tuple[str, str], ...]
    pinned: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — ``{unpinned, pinned, ok}`` (§2.12)."""
        return {
            "unpinned": [list(pair) for pair in self.unpinned],
            "pinned": list(self.pinned),
            "ok": self.ok,
        }


def _looks_like_registry(segment: str) -> bool:
    """A first path segment is a registry host iff it has a ``.`` or ``:`` (§2.12)."""
    return "." in segment or ":" in segment


def parse_image_ref(s: str) -> ImageRef:
    """Split ``[registry/]repo[:tag][@sha256:…]`` into an :class:`ImageRef` (§2.12).

    The digest is peeled off first (everything after ``@``), then the registry is
    recognised only when the first ``/``-segment looks like a host. The remaining
    ``:tag`` is split from the *repository* side, never from a registry ``:port``.
    """
    rest = s.strip()

    digest: str | None = None
    if "@" in rest:
        rest, digest = rest.split("@", 1)

    registry: str | None = None
    if "/" in rest:
        first, remainder = rest.split("/", 1)
        if _looks_like_registry(first):
            registry = first
            rest = remainder

    tag: str | None = None
    if ":" in rest:
        rest, tag = rest.rsplit(":", 1)

    return ImageRef(registry=registry, repository=rest, tag=tag, digest=digest)


def is_pinned(ref: ImageRef) -> bool:
    """True iff a digest is present or the tag is concrete (not ``latest``) (§2.12)."""
    if ref.digest is not None:
        return True
    return ref.tag is not None and ref.tag != _LATEST


def check_pins(images: Mapping[str, str]) -> PinReport:
    """Audit a ``service -> image`` mapping into a :class:`PinReport` (§2.12).

    Iterates in mapping order, collecting unpinned ``(service, image)`` pairs and
    pinned service names; ``ok`` is True exactly when there are no unpinned images.
    """
    unpinned: list[tuple[str, str]] = []
    pinned: list[str] = []
    for service, image in images.items():
        if is_pinned(parse_image_ref(image)):
            pinned.append(service)
        else:
            unpinned.append((service, image))
    return PinReport(unpinned=tuple(unpinned), pinned=tuple(pinned), ok=not unpinned)
