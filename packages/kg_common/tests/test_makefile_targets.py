"""Tests for Makefile required-target coverage — тесты (§2.1)."""

from __future__ import annotations

from kg_common.makefile_targets import (
    DEFAULT_REQUIRED,
    MakefileReport,
    check_required,
    parse_targets,
)


def test_parse_targets_sorted_names() -> None:
    """Two simple rules -> sorted target names, recipes ignored."""
    text = "up:\n\tdocker up\ndown:\n\tdocker down"
    assert parse_targets(text) == ("down", "up")


def test_phony_line_not_a_target() -> None:
    """A ``.PHONY: up`` line registers neither ``.PHONY`` nor ``up``."""
    text = ".PHONY: up\n"
    assert parse_targets(text) == ()


def test_phony_does_not_hide_real_rule() -> None:
    """``.PHONY: up`` plus a real ``up:`` rule -> only ``up`` from the rule."""
    text = ".PHONY: up\nup:\n\tdocker up\n"
    assert parse_targets(text) == ("up",)


def test_deps_are_ignored() -> None:
    """``demo: up seed`` registers ``demo``; prerequisites are not targets."""
    text = "demo: up seed\n\techo done\n"
    assert parse_targets(text) == ("demo",)


def test_indented_recipe_line_not_a_target() -> None:
    """An indented ``\\techo x`` recipe line is never a target."""
    text = "build:\n\techo x\n"
    assert parse_targets(text) == ("build",)


def test_space_indented_line_not_a_target() -> None:
    """A space-indented line that looks like ``name:`` is not a target."""
    text = "build:\n    nested: value\n"
    assert parse_targets(text) == ("build",)


def test_duplicate_targets_deduped() -> None:
    """Repeated rule names collapse to a single sorted entry."""
    text = "up:\n\techo a\nup:\n\techo b\n"
    assert parse_targets(text) == ("up",)


def _full_makefile() -> str:
    """A Makefile declaring every DEFAULT_REQUIRED target."""
    lines = [f"{name}:\n\techo {name}" for name in sorted(DEFAULT_REQUIRED)]
    return "\n".join(lines) + "\n"


def test_check_required_missing_seed() -> None:
    """A Makefile missing ``seed`` -> ``seed`` in missing and ok False."""
    text = _full_makefile().replace("seed:\n\techo seed\n", "")
    report = check_required(text)
    assert "seed" in report.missing
    assert "seed" not in report.present
    assert report.ok is False


def test_check_required_all_present() -> None:
    """A Makefile with all DEFAULT_REQUIRED -> missing empty and ok True."""
    report = check_required(_full_makefile())
    assert report.missing == ()
    assert report.ok is True
    assert set(report.present) == set(DEFAULT_REQUIRED)


def test_missing_is_sorted() -> None:
    """Missing names are returned in sorted order."""
    report = check_required("up:\n\techo up\n")
    assert list(report.missing) == sorted(report.missing)


def test_default_required_frozenset() -> None:
    """DEFAULT_REQUIRED is the frozen §2.1 set."""
    assert isinstance(DEFAULT_REQUIRED, frozenset)
    expected = {
        "up",
        "down",
        "logs",
        "ps",
        "init-db",
        "seed",
        "backup",
        "restore",
        "test",
        "lint",
        "fmt",
    }
    assert expected == DEFAULT_REQUIRED


def test_custom_required_iterable() -> None:
    """``required`` may be any iterable; verdict reflects only those names."""
    report = check_required("up:\n\techo up\n", required=["up", "down"])
    assert report.present == ("up",)
    assert report.missing == ("down",)
    assert report.ok is False


def test_report_as_dict_roundtrip() -> None:
    """``as_dict`` yields a JSON-friendly view of the frozen report."""
    report = MakefileReport(present=("up",), missing=("down",), ok=False)
    assert report.as_dict() == {
        "present": ["up"],
        "missing": ["down"],
        "ok": False,
    }


def test_report_is_frozen() -> None:
    """MakefileReport is immutable."""
    report = check_required(_full_makefile())
    try:
        report.ok = False  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("MakefileReport should be frozen")
