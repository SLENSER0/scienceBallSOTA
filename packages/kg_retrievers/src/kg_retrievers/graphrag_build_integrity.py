"""GraphRAG build integrity check — validate community/report builds.

§11.4 GraphRAG build integrity / Проверка целостности сборки GraphRAG.

RU: Проверяет целостность сборки графа сообществ GraphRAG: наличие сообществ,
корректность отчётов (report) для сообществ, обязательные ключи отчётов и
достаточное число уровней иерархии. Каждая ошибка добавляет описательную строку
и делает отчёт невалидным (ok=False).
EN: Validates a GraphRAG community build: presence of communities, correctness
of per-community reports, required report keys, and a sufficient number of
hierarchy levels. Each failure appends a descriptive error and marks the report
invalid (ok=False).
"""

from __future__ import annotations

from dataclasses import dataclass

# RU: обязательные ключи каждого отчёта сообщества.
# EN: required keys carried by every community report.
_REQUIRED_KEYS: tuple[str, ...] = ("title", "summary", "rank", "level", "community_id")


@dataclass(frozen=True)
class BuildIntegrityReport:
    """Immutable result of a build integrity check / Итог проверки сборки.

    RU: Неизменяемый результат: флаг валидности, число сообществ и отчётов,
    отсортированный кортеж уровней и кортеж описаний ошибок.
    EN: Frozen result: validity flag, community and report counts, a sorted
    tuple of levels, and a tuple of error descriptions.
    """

    ok: bool
    n_communities: int
    n_reports: int
    levels: tuple[int, ...]
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a plain dict view / Вернуть словарное представление."""
        return {
            "ok": bool(self.ok),
            "n_communities": self.n_communities,
            "n_reports": self.n_reports,
            "levels": list(self.levels),
            "errors": list(self.errors),
        }


def check_build(
    communities: list[dict],
    reports: list[dict],
    *,
    min_levels: int = 2,
) -> BuildIntegrityReport:
    """Validate a GraphRAG community build / Проверить сборку сообществ.

    RU: Проверяет, что сообществ > 0, что каждый отчёт несёт обязательные ключи,
    считает n_reports как число отчётов с непустым 'summary' и требует, чтобы
    число различных уровней было >= min_levels. Любая ошибка -> ok=False.
    EN: Checks n_communities > 0, that each report carries required keys, counts
    n_reports as reports with a non-empty 'summary', and requires the distinct
    level count to be >= min_levels. Any failure -> ok=False.
    """
    errors: list[str] = []
    n_communities = len(communities)
    if n_communities == 0:
        errors.append("no communities: build produced 0 communities")

    # RU: собираем уровни из сообществ и отчётов для оценки глубины иерархии.
    # EN: gather levels from communities and reports to assess hierarchy depth.
    level_values: set[int] = set()
    for community in communities:
        level = community.get("level")
        if isinstance(level, int):
            level_values.add(level)

    n_reports = 0
    for index, report in enumerate(reports):
        report_id = report.get("community_id", f"#{index}")
        missing = [key for key in _REQUIRED_KEYS if key not in report]
        if missing:
            errors.append(f"report {report_id!r} missing required keys: {', '.join(missing)}")
        summary = report.get("summary")
        if isinstance(summary, str) and summary.strip():
            n_reports += 1
        else:
            errors.append(f"report {report_id!r} has empty or missing summary")
        report_level = report.get("level")
        if isinstance(report_level, int):
            level_values.add(report_level)

    levels = tuple(sorted(level_values))
    if len(levels) < min_levels:
        errors.append(f"insufficient levels: found {len(levels)} distinct, need >= {min_levels}")

    ok = not errors
    return BuildIntegrityReport(
        ok=ok,
        n_communities=n_communities,
        n_reports=n_reports,
        levels=levels,
        errors=tuple(errors),
    )
