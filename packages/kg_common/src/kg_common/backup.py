"""Backup / restore command builders — планы резервного копирования (§3.9).

Pure-python *builders* for the shell commands that back up and restore the three
persistent stores of the system — Neo4j (graph), PostgreSQL (metadata / catalog)
and Qdrant (vectors). Nothing here **executes** anything: each function returns a
frozen :class:`BackupPlan` describing *what* to run (an ``argv`` list) and *where*
the resulting artifact lands, so the plan can be reviewed, serialized, diffed or
handed to an operator / CI step verbatim. Планы строятся, но не исполняются.

Everything is deterministic and side-effect free:

* No wall-clock — :func:`backup_manifest` derives its ``manifest_id`` from the
  *set of targets*, never from ``datetime.now`` (§3.9 «детерминизм»), so the same
  set of plans always yields the same manifest id.
* No subprocess, no filesystem writes — only string / path assembly.

Public API:

* :class:`BackupPlan`         — frozen ``{target, command, artifact}`` with
  :meth:`BackupPlan.as_dict`.
* :func:`neo4j_dump_plan`     — ``neo4j-admin database dump`` inside a container.
* :func:`postgres_dump_plan`  — ``pg_dump`` of a DSN to a custom-format file.
* :func:`qdrant_snapshot_plan`— ``POST /collections/<c>/snapshots`` (snapshot REST).
* :func:`restore_plan`        — inverse command for a given ``kind`` + artifact.
* :func:`backup_manifest`     — roll up plans into one manifest with a stable id.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from kg_common.ids import short_hash

__all__ = [
    "NEO4J",
    "POSTGRES",
    "QDRANT",
    "BackupPlan",
    "backup_manifest",
    "neo4j_dump_plan",
    "postgres_dump_plan",
    "qdrant_snapshot_plan",
    "restore_plan",
]

# Store kinds — виды хранилищ (§3.9). Used as the ``kind`` selector for restores.
NEO4J = "neo4j"
POSTGRES = "postgres"
QDRANT = "qdrant"

_KINDS = (NEO4J, POSTGRES, QDRANT)


@dataclass(frozen=True)
class BackupPlan:
    """A single, immutable backup/restore command spec — план команды (§3.9).

    ``target`` is a stable logical identifier for what the plan acts on (e.g.
    ``"neo4j:kg@neo4j"``, ``"postgres:scienceball"``, ``"qdrant:materials"``); it
    is the key from which :func:`backup_manifest` derives a deterministic id.
    ``command`` is the ``argv`` list to run (never a shell string — no quoting
    ambiguity). ``artifact`` is the path / URL the command produces or consumes.

    The dataclass is frozen so a plan can be passed around and serialized safely;
    it is a plain record — building is done by the module-level functions below.
    """

    target: str
    command: list[str]
    artifact: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — ``{target, command, artifact}`` (§3.9)."""
        return {
            "target": self.target,
            "command": list(self.command),
            "artifact": self.artifact,
        }


def _artifact_under(out_dir: str, name: str) -> str:
    """Join ``out_dir`` and a file ``name`` as a POSIX path — артефакт в каталоге (§3.9)."""
    return str(PurePosixPath(out_dir) / name)


def neo4j_dump_plan(container: str, out_dir: str, *, database: str = "neo4j") -> BackupPlan:
    """Plan a Neo4j offline dump — ``neo4j-admin database dump`` (§3.9).

    Runs ``neo4j-admin database dump`` *inside* the given docker ``container`` and
    writes the dump into ``out_dir`` (``--to-path``); the tool names the file
    ``<database>.dump``, so the artifact is deterministically
    ``<out_dir>/<database>.dump``. ``database`` defaults to the standard ``"neo4j"``.

    ``neo4j_dump_plan("neo4j", "/backups").command`` contains ``neo4j-admin``,
    ``database`` and ``dump`` and the artifact is ``/backups/neo4j.dump``.
    """
    artifact = _artifact_under(out_dir, f"{database}.dump")
    command = [
        "docker",
        "exec",
        container,
        "neo4j-admin",
        "database",
        "dump",
        database,
        "--to-path",
        out_dir,
    ]
    return BackupPlan(target=f"neo4j:{database}@{container}", command=command, artifact=artifact)


def _dsn_dbname(dsn: str) -> str:
    """Extract the database name from a libpq/SQLAlchemy DSN — имя БД из DSN (§3.9)."""
    path = urlsplit(dsn).path.lstrip("/")
    # A DSN may carry query params after the db name; keep only the first segment.
    return path.split("/")[0] or "postgres"


def postgres_dump_plan(dsn: str, out_dir: str) -> BackupPlan:
    """Plan a PostgreSQL dump — ``pg_dump`` in custom format (§3.9).

    Dumps the database referenced by ``dsn`` to a custom-format archive named
    after the DSN's database, i.e. ``<out_dir>/<dbname>.dump``. Custom format
    (``--format=custom``) is compressed and restorable selectively via
    :func:`restore_plan` (``pg_restore``). The DSN is passed through to
    ``--dbname`` verbatim, so any embedded credentials travel with the command.

    ``postgres_dump_plan("postgresql://u@h/kg", "/b").command`` contains ``pg_dump``
    and the artifact is ``/b/kg.dump``.
    """
    dbname = _dsn_dbname(dsn)
    artifact = _artifact_under(out_dir, f"{dbname}.dump")
    command = [
        "pg_dump",
        "--dbname",
        dsn,
        "--format",
        "custom",
        "--file",
        artifact,
    ]
    return BackupPlan(target=f"postgres:{dbname}", command=command, artifact=artifact)


def _snapshots_endpoint(url: str, collection: str) -> str:
    """REST endpoint for a collection's snapshots — точка REST снапшотов (§3.9)."""
    return f"{url.rstrip('/')}/collections/{collection}/snapshots"


def qdrant_snapshot_plan(url: str, collection: str) -> BackupPlan:
    """Plan a Qdrant snapshot — ``POST /collections/<c>/snapshots`` (§3.9).

    Qdrant snapshots are created *server-side* via its REST API: a ``POST`` to
    ``<url>/collections/<collection>/snapshots`` makes the node write a snapshot
    file it manages itself. The artifact is therefore the snapshots endpoint (the
    server assigns the concrete, timestamped filename), and the command is a
    ``curl`` ``POST`` to that endpoint.

    ``qdrant_snapshot_plan("http://localhost:6333", "materials").command`` hits
    ``.../collections/materials/snapshots``.
    """
    endpoint = _snapshots_endpoint(url, collection)
    command = ["curl", "-sS", "-X", "POST", endpoint]
    return BackupPlan(target=f"qdrant:{collection}", command=command, artifact=endpoint)


def restore_plan(kind: str, artifact: str) -> BackupPlan:
    """Plan the inverse (restore) command for a backup artifact — восстановление (§3.9).

    ``kind`` selects the store (:data:`NEO4J` / :data:`POSTGRES` / :data:`QDRANT`)
    and thus the tool used to load ``artifact``:

    * ``neo4j``    — ``neo4j-admin database load <db> --from-path <dir>``; the
      database name is taken from the artifact's file stem (``neo4j.dump`` → ``neo4j``).
    * ``postgres`` — ``pg_restore`` of the custom-format archive.
    * ``qdrant``   — ``curl PUT <snapshots-endpoint>/recover`` (snapshot recover REST).

    An unknown ``kind`` raises :class:`ValueError`. The returned plan carries the
    same ``artifact`` it restores from and a ``restore:``-prefixed target.
    """
    art = PurePosixPath(artifact)
    if kind == NEO4J:
        database = art.stem or "neo4j"
        command = [
            "neo4j-admin",
            "database",
            "load",
            database,
            "--from-path",
            str(art.parent),
            "--overwrite-destination=true",
        ]
    elif kind == POSTGRES:
        command = ["pg_restore", "--clean", "--if-exists", artifact]
    elif kind == QDRANT:
        command = ["curl", "-sS", "-X", "PUT", f"{artifact.rstrip('/')}/recover"]
    else:
        raise ValueError(f"unknown backup kind: {kind!r} (expected one of {_KINDS})")
    return BackupPlan(target=f"restore:{kind}:{art.name}", command=command, artifact=artifact)


def backup_manifest(plans: Sequence[BackupPlan]) -> dict[str, object]:
    """Roll up plans into one manifest with a deterministic id — манифест (§3.9).

    The manifest lists every plan's ``target`` and ``artifact`` and embeds each
    plan's :meth:`BackupPlan.as_dict`. Its ``manifest_id`` is a stable hash of the
    *sorted, de-duplicated target set* — **not** a timestamp — so the same set of
    plans always produces the same id regardless of the order they were passed in
    (§3.9 «детерминизм, без настенных часов»).

    ``targets`` is returned sorted/de-duplicated; ``artifacts`` follows the input
    plan order (so callers can correlate positionally).
    """
    targets = sorted({p.target for p in plans})
    manifest_id = short_hash("\n".join(targets), 16)
    return {
        "manifest_id": manifest_id,
        "targets": targets,
        "artifacts": [p.artifact for p in plans],
        "plans": [p.as_dict() for p in plans],
    }
