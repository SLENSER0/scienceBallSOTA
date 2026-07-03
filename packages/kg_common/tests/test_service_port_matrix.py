"""Tests for the Docker Compose port matrix — hand-checkable (§2.4)."""

from __future__ import annotations

from kg_common.service_port_matrix import (
    PortBinding,
    PortMatrixReport,
    check_collisions,
    parse_ports,
)


def test_parse_symmetric_host_equals_container() -> None:
    """``'8000:8000'`` → host==container==8000."""
    bindings = parse_ports({"api": ["8000:8000"]})
    assert len(bindings) == 1
    assert bindings[0].host_port == 8000
    assert bindings[0].container_port == 8000
    assert bindings[0].service == "api"


def test_parse_lone_token_means_equal() -> None:
    """A lone token ``'6379'`` → host==container==6379."""
    bindings = parse_ports({"r": ["6379"]})
    assert len(bindings) == 1
    assert bindings[0].host_port == bindings[0].container_port == 6379


def test_parse_remap_host_to_container() -> None:
    """``'3000:80'`` → host 3000, container 80."""
    bindings = parse_ports({"grafana": ["3000:80"]})
    assert bindings[0].host_port == 3000
    assert bindings[0].container_port == 80


def test_bindings_sorted_ascending() -> None:
    """Bindings come back sorted by host_port ascending."""
    bindings = parse_ports({"z": ["9000"], "a": ["3000"], "m": ["6333"]})
    assert [b.host_port for b in bindings] == [3000, 6333, 9000]


def test_two_services_same_host_port_collide() -> None:
    """Two distinct services on host 9000 → single collision, ok False."""
    bindings = parse_ports({"a": ["9000:9000"], "b": ["9000:8080"]})
    report = check_collisions(bindings)
    assert report.collisions == ((9000, ("a", "b")),)
    assert report.ok is False


def test_three_services_distinct_ports_ok() -> None:
    """Three services on distinct host ports → no collisions, ok True."""
    bindings = parse_ports({"a": ["8000"], "b": ["6333"], "c": ["3000"]})
    report = check_collisions(bindings)
    assert report.collisions == ()
    assert report.ok is True


def test_collisions_sorted_ascending_by_port() -> None:
    """Multiple collisions are returned sorted ascending by host port."""
    bindings = parse_ports(
        {
            "a": ["9000", "5000"],
            "b": ["9000", "5000"],
        }
    )
    report = check_collisions(bindings)
    assert [port for port, _ in report.collisions] == [5000, 9000]
    assert report.ok is False


def test_same_service_twice_is_not_a_collision() -> None:
    """A collision needs >1 *distinct* service — same service twice is fine."""
    bindings = (
        PortBinding("api", 8000, 8000),
        PortBinding("api", 8000, 9000),
    )
    report = check_collisions(bindings)
    assert report.collisions == ()
    assert report.ok is True


def test_report_as_dict_shape() -> None:
    """``as_dict()['ok']`` is a bool and ``['bindings']`` length matches input."""
    bindings = parse_ports({"a": ["8000"], "b": ["6333"], "c": ["3000"]})
    report = check_collisions(bindings)
    payload = report.as_dict()
    assert isinstance(payload["ok"], bool)
    assert len(payload["bindings"]) == len(bindings) == 3


def test_report_as_dict_collision_payload() -> None:
    """Collision payload carries host_port + services list."""
    bindings = parse_ports({"a": ["9000:9000"], "b": ["9000:8080"]})
    report = check_collisions(bindings)
    payload = report.as_dict()
    assert payload["ok"] is False
    assert payload["collisions"] == [{"host_port": 9000, "services": ["a", "b"]}]


def test_binding_as_dict_roundtrip() -> None:
    """PortBinding.as_dict exposes all three fields."""
    binding = PortBinding("qdrant", 6333, 6333)
    assert binding.as_dict() == {
        "service": "qdrant",
        "host_port": 6333,
        "container_port": 6333,
    }


def test_report_type() -> None:
    """check_collisions returns a PortMatrixReport."""
    report = check_collisions(parse_ports({"a": ["1000"]}))
    assert isinstance(report, PortMatrixReport)
