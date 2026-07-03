"""Pure-python Dockerfile lint — линт Dockerfile для каждого сервиса (§2.3).

The §2.3 build baseline asks every service image to be *safe by default*: it
must drop root, expose a container-level healthcheck, and pin its base image
so builds are reproducible. This module checks those three rules on Dockerfile
*text* — без Docker-демона, без сети, без файловой системы — so CI can gate a
Dockerfile deterministically and by hand.

Rules emitted by :func:`lint_dockerfile`:

* ``DL_ROOT_USER``      — the image runs as root: no ``USER`` instruction at
  all, or the last ``USER`` is ``root`` («контейнер работает от root»).
* ``DL_NO_HEALTHCHECK`` — no ``HEALTHCHECK`` instruction («нет healthcheck»).
* ``DL_BASE_UNPINNED``  — some ``FROM`` base image is unpinned: no tag, or the
  tag is ``latest`` («базовый образ не закреплён»). A ``FROM`` that only
  references an earlier build stage by name is *not* a base image and is
  ignored.

Findings are returned sorted by :attr:`DockerfileFinding.rule`, so the output
is stable regardless of instruction order.

Public API:

* :class:`DockerfileFinding` — frozen ``(rule, severity, message)`` with
  :meth:`~DockerfileFinding.as_dict`.
* :func:`from_images`   — every ``FROM`` target in order.
* :func:`final_user`    — the last ``USER`` value, or ``None``.
* :func:`has_healthcheck` — whether any ``HEALTHCHECK`` is present.
* :func:`lint_dockerfile` — the three rules above, rule-sorted.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DockerfileFinding",
    "from_images",
    "final_user",
    "has_healthcheck",
    "lint_dockerfile",
]


@dataclass(frozen=True, slots=True)
class DockerfileFinding:
    """One Dockerfile lint finding — одно замечание линтера (§2.3).

    ``rule`` is a stable ``DL_*`` identifier; ``severity`` is a short label
    («error»/«warning»); ``message`` is a human-readable RU/EN explanation. A
    plain frozen value so it can be hashed, compared and serialized for a CI
    report.
    """

    rule: str
    severity: str
    message: str

    def as_dict(self) -> dict[str, str]:
        """JSON-friendly view — строка отчёта CI (§2.3)."""
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
        }


def _instruction_lines(text: str) -> list[tuple[str, str]]:
    """Split ``text`` into ``(keyword_upper, remainder)`` instruction pairs.

    Blank lines and ``#`` comments are dropped; the instruction keyword is
    upper-cased for case-insensitive matching, the remainder is stripped.
    Разбор строк Dockerfile без учёта регистра ключевого слова.
    """
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        keyword = parts[0].upper()
        remainder = parts[1].strip() if len(parts) > 1 else ""
        out.append((keyword, remainder))
    return out


def from_images(text: str) -> tuple[str, ...]:
    """Return every ``FROM`` target image in order — все цели ``FROM`` (§2.3).

    For ``FROM python:3.12 AS build`` the target is ``python:3.12`` (the ``AS
    <stage>`` alias and any ``--platform`` flag are dropped). Order is the order
    of appearance, so a multistage file yields one entry per stage.
    """
    images: list[str] = []
    for keyword, remainder in _instruction_lines(text):
        if keyword != "FROM":
            continue
        tokens = [t for t in remainder.split() if not t.startswith("--")]
        if not tokens:
            continue
        images.append(tokens[0])
    return tuple(images)


def final_user(text: str) -> str | None:
    """Return the last ``USER`` value, or ``None`` — итоговый ``USER`` (§2.3).

    The effective runtime user is whatever the *last* ``USER`` instruction
    sets. ``None`` means no ``USER`` was declared at all.
    """
    result: str | None = None
    for keyword, remainder in _instruction_lines(text):
        if keyword == "USER" and remainder:
            result = remainder.split()[0]
    return result


def has_healthcheck(text: str) -> bool:
    """Whether any ``HEALTHCHECK`` is present — есть ли healthcheck (§2.3)."""
    return any(keyword == "HEALTHCHECK" for keyword, _ in _instruction_lines(text))


def _is_unpinned(image: str, stages: frozenset[str]) -> bool:
    """Whether a ``FROM`` base image is unpinned — не закреплён ли образ (§2.3).

    A ``FROM`` that references an earlier build *stage* by name is not a base
    image and is never unpinned. Otherwise the image is unpinned when it has no
    ``:tag`` or its tag is ``latest``. A digest pin (``@sha256:…``) counts as
    pinned. The registry-host port colon (``host:5000/img``) is not a tag.
    """
    if image in stages:
        return False
    if "@" in image:  # digest pin, e.g. python@sha256:...
        return False
    # A tag colon lives in the last path segment, after any registry host.
    last_segment = image.rsplit("/", 1)[-1]
    if ":" not in last_segment:
        return True
    tag = last_segment.rsplit(":", 1)[1]
    return tag == "latest"


def lint_dockerfile(text: str) -> tuple[DockerfileFinding, ...]:
    """Lint Dockerfile ``text`` for the three §2.3 rules — линт (§2.3).

    Emits at most one finding per rule:

    * ``DL_ROOT_USER`` when :func:`final_user` is ``None`` or ``root``;
    * ``DL_NO_HEALTHCHECK`` when :func:`has_healthcheck` is false;
    * ``DL_BASE_UNPINNED`` when any base ``FROM`` image is unpinned.

    A fully-good multistage file (pinned base, non-root final ``USER``,
    ``HEALTHCHECK``) yields ``()``. Findings are sorted by
    :attr:`DockerfileFinding.rule` for deterministic output.
    """
    findings: list[DockerfileFinding] = []

    user = final_user(text)
    if user is None:
        findings.append(
            DockerfileFinding(
                "DL_ROOT_USER",
                "error",
                "No USER instruction: image runs as root — образ работает от root.",
            )
        )
    elif user == "root":
        findings.append(
            DockerfileFinding(
                "DL_ROOT_USER",
                "error",
                "Final USER is root: drop privileges — сбросьте привилегии.",
            )
        )

    if not has_healthcheck(text):
        findings.append(
            DockerfileFinding(
                "DL_NO_HEALTHCHECK",
                "warning",
                "No HEALTHCHECK instruction — нет проверки здоровья контейнера.",
            )
        )

    images = from_images(text)
    stages = frozenset(_stage_aliases(text))
    if any(_is_unpinned(image, stages) for image in images):
        findings.append(
            DockerfileFinding(
                "DL_BASE_UNPINNED",
                "warning",
                "Base image is unpinned or ':latest' — закрепите тег базового образа.",
            )
        )

    return tuple(sorted(findings, key=lambda f: f.rule))


def _stage_aliases(text: str) -> tuple[str, ...]:
    """Return all ``AS <stage>`` aliases — имена стадий сборки (§2.3)."""
    aliases: list[str] = []
    for keyword, remainder in _instruction_lines(text):
        if keyword != "FROM":
            continue
        tokens = remainder.split()
        for i, token in enumerate(tokens):
            if token.upper() == "AS" and i + 1 < len(tokens):
                aliases.append(tokens[i + 1])
    return tuple(aliases)
