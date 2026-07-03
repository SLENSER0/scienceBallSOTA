"""Hand-checkable tests for the §2.3 Dockerfile lint — тесты линтера.

Каждый кейс проверяется вручную по правилам §2.3: root-пользователь,
healthcheck, закрепление базового образа. Findings отсортированы по имени
правила, что делает вывод детерминированным.
"""

from __future__ import annotations

from kg_common.dockerfile_lint import (
    DockerfileFinding,
    final_user,
    from_images,
    has_healthcheck,
    lint_dockerfile,
)

GOOD_MULTISTAGE = (
    "FROM python:3.12 AS build\n"
    "RUN pip install .\n"
    "FROM python:3.12\n"
    "COPY --from=build /app /app\n"
    "USER app\n"
    "HEALTHCHECK CMD curl -f http://localhost/health || exit 1\n"
)


def _rules(text: str) -> tuple[str, ...]:
    return tuple(f.rule for f in lint_dockerfile(text))


def test_from_images_collects_all_targets_in_order() -> None:
    assert from_images("FROM python:3.12 AS build\nFROM build") == (
        "python:3.12",
        "build",
    )


def test_from_images_drops_platform_flag() -> None:
    assert from_images("FROM --platform=linux/amd64 alpine:3.20 AS base") == ("alpine:3.20",)


def test_final_user_returns_last_user_value() -> None:
    assert final_user("USER root\nUSER app") == "app"


def test_final_user_none_when_absent() -> None:
    assert final_user("FROM python:3.12\nRUN true") is None


def test_has_healthcheck_true_when_present() -> None:
    assert has_healthcheck("FROM python:3.12\nHEALTHCHECK CMD echo ok") is True


def test_has_healthcheck_false_when_absent() -> None:
    assert has_healthcheck("FROM python:3.12\nUSER app") is False


def test_no_user_yields_root_user_finding() -> None:
    text = "FROM python:3.12\nHEALTHCHECK CMD true\n"
    assert "DL_ROOT_USER" in _rules(text)


def test_user_root_yields_root_user_finding() -> None:
    text = "FROM python:3.12\nUSER root\nHEALTHCHECK CMD true\n"
    assert "DL_ROOT_USER" in _rules(text)


def test_latest_base_yields_unpinned_finding() -> None:
    text = "FROM python:latest\nUSER app\nHEALTHCHECK CMD true\n"
    assert "DL_BASE_UNPINNED" in _rules(text)


def test_untagged_base_yields_unpinned_finding() -> None:
    text = "FROM python\nUSER app\nHEALTHCHECK CMD true\n"
    assert "DL_BASE_UNPINNED" in _rules(text)


def test_pinned_base_yields_no_unpinned_finding() -> None:
    text = "FROM python:3.12\nUSER app\nHEALTHCHECK CMD true\n"
    assert "DL_BASE_UNPINNED" not in _rules(text)


def test_missing_healthcheck_yields_finding() -> None:
    text = "FROM python:3.12\nUSER app\n"
    assert "DL_NO_HEALTHCHECK" in _rules(text)


def test_good_multistage_file_is_clean() -> None:
    assert lint_dockerfile(GOOD_MULTISTAGE) == ()


def test_registry_host_port_is_not_a_tag() -> None:
    # host:5000 is a registry port, not an image tag → untagged image → unpinned
    text = "FROM registry.local:5000/python\nUSER app\nHEALTHCHECK CMD true\n"
    assert "DL_BASE_UNPINNED" in _rules(text)


def test_registry_host_port_with_pinned_tag_is_clean() -> None:
    text = "FROM registry.local:5000/python:3.12\nUSER app\nHEALTHCHECK CMD true\n"
    assert "DL_BASE_UNPINNED" not in _rules(text)


def test_digest_pin_is_not_unpinned() -> None:
    text = "FROM python@sha256:abc123\nUSER app\nHEALTHCHECK CMD true\n"
    assert "DL_BASE_UNPINNED" not in _rules(text)


def test_findings_sorted_by_rule_name() -> None:
    # No USER, no HEALTHCHECK, latest base → all three rules, rule-sorted.
    text = "FROM python:latest\nRUN true\n"
    rules = _rules(text)
    assert rules == ("DL_BASE_UNPINNED", "DL_NO_HEALTHCHECK", "DL_ROOT_USER")
    assert list(rules) == sorted(rules)


def test_stage_reference_from_is_not_unpinned() -> None:
    # Second FROM references the 'build' stage by name, not a base image.
    assert lint_dockerfile(GOOD_MULTISTAGE) == ()


def test_finding_as_dict_round_trip() -> None:
    finding = DockerfileFinding("DL_ROOT_USER", "error", "runs as root")
    assert finding.as_dict() == {
        "rule": "DL_ROOT_USER",
        "severity": "error",
        "message": "runs as root",
    }


def test_lint_returns_tuple_of_findings() -> None:
    result = lint_dockerfile("FROM python:latest\n")
    assert isinstance(result, tuple)
    assert all(isinstance(f, DockerfileFinding) for f in result)
