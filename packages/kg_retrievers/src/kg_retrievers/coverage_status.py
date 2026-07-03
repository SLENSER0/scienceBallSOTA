"""Coverage-cell status classifier for the coverage matrix (§24.15).

Матрица покрытия сводит совокупность знаний к ячейкам вида
``material × process × condition × property``. Каждая ячейка несёт метаданные:
сколько свидетельств её подтверждает (``evidence_count``), сколько из них
верифицировано (``verified_count``), год последнего обновления (``latest_year``)
и агрегированную уверенность (``confidence``). Этот модуль сворачивает эти
сигналы в один ярлык ``coverage_status`` (§24.15 «coverage status, latest
update, confidence»).

Модуль чисто-питоновский и намеренно отделён от графового ``coverage_matrix_3d``:
здесь нет обращений к хранилищу, только классификация одной ячейки.

Правила (в порядке приоритета):

- ``evidence_count == 0`` → ``'absent'`` (данных нет вовсе);
- ``latest_year`` старше ``stale_years`` → ``'stale'`` (``is_stale`` True);
- ``verified_count > 0`` и ``confidence >= verified_conf`` → ``'verified'``;
- ``evidence_count <= thin_max`` → ``'thin'`` (свидетельств мало);
- иначе → ``'covered'``.

A pure-python classifier that folds a coverage cell's evidence count,
verification count, recency and confidence into a single ``coverage_status``
label. Distinct from the graph-building ``coverage_matrix_3d``: no store access.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "0.1.0"

# Status labels -------------------------------------------------------------
VERIFIED = "verified"
COVERED = "covered"
THIN = "thin"
STALE = "stale"
ABSENT = "absent"

# All statuses this classifier may emit.
STATUS_LABELS: tuple[str, ...] = (VERIFIED, COVERED, THIN, STALE, ABSENT)

# Defaults (recency window, thinness threshold, verified-confidence floor).
DEFAULT_STALE_YEARS = 5
DEFAULT_THIN_MAX = 1
DEFAULT_VERIFIED_CONF = 0.7


@dataclass(frozen=True)
class CoverageStatus:
    """Classified status of one coverage-matrix cell (§24.15).

    ``status`` is one of ``STATUS_LABELS``; ``confidence`` is carried through
    from the input unchanged so downstream UI can render it alongside the label.
    """

    status: str
    evidence_count: int
    verified_count: int
    is_stale: bool
    confidence: float

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "verified_count": self.verified_count,
            "is_stale": self.is_stale,
            "confidence": self.confidence,
        }


def classify_cell(
    evidence_count: int,
    verified_count: int,
    latest_year: int | None,
    confidence: float,
    *,
    current_year: int,
    stale_years: int = DEFAULT_STALE_YEARS,
    thin_max: int = DEFAULT_THIN_MAX,
    verified_conf: float = DEFAULT_VERIFIED_CONF,
) -> CoverageStatus:
    """Classify one coverage cell into a :class:`CoverageStatus` label.

    Правила по приоритету: пустая ячейка (``evidence_count == 0``) → ``'absent'``;
    устаревшая (``latest_year`` старше ``stale_years`` относительно
    ``current_year``) → ``'stale'`` с ``is_stale`` True; подтверждённая
    (``verified_count > 0`` и ``confidence >= verified_conf``) → ``'verified'``;
    скудная (``evidence_count <= thin_max``) → ``'thin'``; иначе → ``'covered'``.

    Граница свежести включающая: ``latest_year == current_year - stale_years``
    ещё не считается устаревшей. ``confidence`` переносится в результат без
    изменений.
    """
    # Cell has no evidence at all — nothing to age, verify, or count.
    if evidence_count == 0:
        return CoverageStatus(
            status=ABSENT,
            evidence_count=evidence_count,
            verified_count=verified_count,
            is_stale=False,
            confidence=confidence,
        )

    # Staleness: only meaningful when we know the latest update year. A cell is
    # stale once it is strictly older than the (inclusive) staleness boundary.
    is_stale = latest_year is not None and latest_year < (current_year - stale_years)
    if is_stale:
        return CoverageStatus(
            status=STALE,
            evidence_count=evidence_count,
            verified_count=verified_count,
            is_stale=True,
            confidence=confidence,
        )

    if verified_count > 0 and confidence >= verified_conf:
        status = VERIFIED
    elif evidence_count <= thin_max:
        status = THIN
    else:
        status = COVERED

    return CoverageStatus(
        status=status,
        evidence_count=evidence_count,
        verified_count=verified_count,
        is_stale=False,
        confidence=confidence,
    )
