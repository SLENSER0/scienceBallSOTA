"""Tests for the env-var reference sync checker — тесты сверки (§19.12)."""

from __future__ import annotations

from kg_common.env_reference import (
    EnvVarSpec,
    ReconcileReport,
    documented_names,
    extract_env_names,
    reconcile,
)


def test_extract_all_four_call_forms() -> None:
    """(1) All four access forms are found, with either quote style."""
    source = """
    a = os.environ['ALPHA']
    b = os.environ["BRAVO"]
    c = os.environ.get('CHARLIE')
    d = os.environ.get("DELTA")
    e = os.getenv('ECHO')
    f = os.getenv("FOXTROT")
    g = getenv('GOLF')
    h = getenv("HOTEL")
    """
    names = extract_env_names(source)
    assert names == frozenset(
        {"ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL"}
    )


def test_plain_string_literal_not_extracted() -> None:
    """(2) A bare string that is not an env access is ignored."""
    source = """
    greeting = "NOT_AN_ENV_VAR"
    label = 'ALSO_NOT_ONE'
    real = os.getenv("REAL_VAR")
    # os.environ mentioned in prose but data.get('KEY') is a dict, not environ
    other = data.get('DICT_KEY')
    """
    names = extract_env_names(source)
    assert names == frozenset({"REAL_VAR"})
    assert "NOT_AN_ENV_VAR" not in names
    assert "DICT_KEY" not in names


def test_reconcile_reports_undocumented() -> None:
    """(3) Names read in code but missing from docs land in ``undocumented``."""
    code = frozenset({"IN_BOTH", "CODE_ONLY"})
    docs = frozenset({"IN_BOTH"})
    report = reconcile(code, docs)
    assert report.undocumented == ("CODE_ONLY",)
    assert report.unused == ()


def test_reconcile_reports_unused() -> None:
    """(4) Documented names absent from code land in ``unused``."""
    code = frozenset({"IN_BOTH"})
    docs = frozenset({"IN_BOTH", "DOCS_ONLY"})
    report = reconcile(code, docs)
    assert report.undocumented == ()
    assert report.unused == ("DOCS_ONLY",)


def test_reconcile_empty_when_aligned() -> None:
    """(5) Both tuples empty when code and docs match exactly."""
    aligned = frozenset({"ALPHA", "BRAVO"})
    report = reconcile(aligned, aligned)
    assert report.undocumented == ()
    assert report.unused == ()
    assert report == ReconcileReport(undocumented=(), unused=())


def test_spec_as_dict_preserves_secret_and_none_default() -> None:
    """(6) ``as_dict`` preserves the secret flag and a ``None`` default."""
    spec = EnvVarSpec(name="API_TOKEN", required=True, secret=True, default=None)
    assert spec.as_dict() == {
        "name": "API_TOKEN",
        "required": True,
        "secret": True,
        "default": None,
    }


def test_reconcile_output_is_sorted() -> None:
    """(7) Both tuples are sorted deterministically regardless of input order."""
    code = frozenset({"ZULU", "ALPHA", "MIKE"})
    docs = frozenset({"YANKEE", "BRAVO", "NOVEMBER"})
    report = reconcile(code, docs)
    assert report.undocumented == ("ALPHA", "MIKE", "ZULU")
    assert report.unused == ("BRAVO", "NOVEMBER", "YANKEE")
    assert list(report.undocumented) == sorted(report.undocumented)
    assert list(report.unused) == sorted(report.unused)


def test_documented_names_collects_spec_names() -> None:
    """``documented_names`` collapses a registry to its name set."""
    specs = [
        EnvVarSpec(name="ALPHA", required=True, secret=False, default=None),
        EnvVarSpec(name="BRAVO", required=False, secret=True, default="x"),
    ]
    assert documented_names(specs) == frozenset({"ALPHA", "BRAVO"})


def test_end_to_end_extract_then_reconcile() -> None:
    """End-to-end: extract code names, reconcile against a real registry."""
    source = """
    db = os.environ['DB_URL']
    key = os.getenv("SECRET_KEY")
    """
    specs = [
        EnvVarSpec(name="DB_URL", required=True, secret=False, default=None),
        EnvVarSpec(name="LOG_LEVEL", required=False, secret=False, default="INFO"),
    ]
    report = reconcile(extract_env_names(source), documented_names(specs))
    assert report.undocumented == ("SECRET_KEY",)
    assert report.unused == ("LOG_LEVEL",)
