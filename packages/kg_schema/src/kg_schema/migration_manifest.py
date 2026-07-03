"""Graph migration schema & versioning manifest (§3.15 — ordered Cypher migrations).

``schema_version.py`` следит за узлом ``SchemaVersion`` (какая версия схемы сейчас в
силе), но *не перечисляет* сами миграции. Каталог миграций — это упорядоченный набор
файлов ``NNNN_<name>.cypher`` (например ``0001_constraints.cypher``): каждый несёт
номер (*number*, порядок применения) и имя (*name*, человекочитаемая метка), а также
контрольную сумму (*checksum*) своего содержимого. Этот модуль строит из таких файлов
:class:`MigrationManifest` и вычисляет, какие миграции ещё *не применены* (*pending*).

Модуль чистый (*pure*): он не читает файловую систему и не ходит на сервер. На вход
:func:`build_manifest` принимает отображение ``filename -> content`` (карту имён в
содержимое), а :func:`pending` сравнивает контрольные суммы каталога с множеством уже
применённых сумм (``applied_checksums``). Так логику версионирования можно проверять
детерминированно, без Kuzu и без диска.

Checksum — это SHA-256 содержимого миграции: одинаковый текст даёт одинаковую сумму,
изменённый — другую, поэтому сумма служит и идентификатором «этой ровно версии»
миграции при идемпотентном применении (§3.15 / §23.4).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Имя файла миграции: NNNN_<name>.cypher, где NNNN — номер (>=1 цифра), name — метка.
# Migration filename pattern — leading zero-padded number, snake/kebab name, .cypher.
_FILENAME_RE = re.compile(r"^(\d+)_([^.][^/]*?)\.cypher$")


@dataclass(frozen=True)
class Migration:
    """One ordered Cypher migration (§3.15).

    Attributes
    ----------
    number:
        Порядковый номер применения (*application order*) — из префикса ``NNNN``.
    name:
        Человекочитаемая метка (*human label*) — часть имени файла после номера.
    filename:
        Исходное имя файла (``NNNN_<name>.cypher``).
    checksum:
        Контрольная сумма содержимого (*content checksum*, SHA-256 hex).
    """

    number: int
    name: str
    filename: str
    checksum: str

    def as_dict(self) -> dict[str, Any]:
        """Flat property-map for a ``:Migration`` node (§8.2 — Kuzu-friendly)."""
        return {
            "number": self.number,
            "name": self.name,
            "filename": self.filename,
            "checksum": self.checksum,
        }


@dataclass(frozen=True)
class MigrationManifest:
    """Ordered set of migrations (*manifest*) — sorted ascending by number (§3.15)."""

    migrations: tuple[Migration, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise the whole manifest as a list of per-migration property-maps."""
        return {"migrations": [m.as_dict() for m in self.migrations]}


def parse_migration_filename(name: str) -> tuple[int, str]:
    """Parse ``NNNN_<name>.cypher`` into ``(number, name)`` (§3.15).

    Разбирает имя файла миграции на числовой номер и текстовую метку.

    Raises
    ------
    ValueError
        Если имя не соответствует шаблону ``NNNN_<name>.cypher``.
    """
    match = _FILENAME_RE.match(name)
    if match is None:
        raise ValueError(f"not a migration filename: {name!r}")
    return int(match.group(1)), match.group(2)


def checksum(content: str) -> str:
    """Return the SHA-256 hex digest of migration ``content`` (§3.15).

    Детерминированная контрольная сумма содержимого: одинаковый текст — одинаковая
    сумма, разный текст — разная.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_manifest(files: Mapping[str, str]) -> MigrationManifest:
    """Build a sorted :class:`MigrationManifest` from ``filename -> content`` (§3.15).

    Строит каталог миграций из карты «имя файла -> содержимое», сортируя по номеру и
    вычисляя контрольную сумму каждого файла.

    Raises
    ------
    ValueError
        Если имя файла некорректно или два файла имеют один и тот же номер
        (*duplicate migration number*).
    """
    by_number: dict[int, Migration] = {}
    for filename, content in files.items():
        number, name = parse_migration_filename(filename)
        if number in by_number:
            raise ValueError(f"duplicate migration number: {number:04d}")
        by_number[number] = Migration(
            number=number,
            name=name,
            filename=filename,
            checksum=checksum(content),
        )
    ordered = tuple(by_number[n] for n in sorted(by_number))
    return MigrationManifest(migrations=ordered)


def pending(manifest: MigrationManifest, applied_checksums: set[str]) -> list[Migration]:
    """Return not-yet-applied migrations in ascending order (§3.15).

    Возвращает миграции, чьих контрольных сумм нет в ``applied_checksums``, в порядке
    возрастания номера — то, что ещё предстоит применить.
    """
    return [m for m in manifest.migrations if m.checksum not in applied_checksums]
