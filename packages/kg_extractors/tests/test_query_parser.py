"""Query parser on the 4 acceptance queries (§24.9) + entity resolution."""

from __future__ import annotations

from kg_extractors.entity_resolution import get_resolver
from kg_extractors.query_parser import parse_query

Q_WATER = (
    "Какие методы обессоливания воды подходят для обогатительной фабрики, если "
    "исходная вода содержит сульфаты, хлориды, Ca, Mg, Na по 200–300 мг/л, а "
    "требуемый сухой остаток — ≤1000 мг/дм³?"
)
Q_NICKEL = (
    "Какие технические решения организации циркуляции католита при "
    "электроэкстракции никеля описаны в мировой практике, и какая скорость "
    "потока считается оптимальной?"
)
Q_PGM = (
    "Покажите все эксперименты и публикации по распределению Au, Ag и МПГ между "
    "медным и никелевым штейном и шлаком за последние 5 лет"
)
Q_INJECTION = (
    "Какие способы закачки шахтных вод в глубокие горизонты применялись в "
    "России и за рубежом, и каковы их технико-экономические показатели?"
)


def test_water_query() -> None:
    q = parse_query(Q_WATER)
    ids = {e.id for e in q.entities}
    assert {"desalination", "sulfates", "chlorides", "calcium", "magnesium", "sodium"} <= ids
    ops = {c.operator for c in q.numeric_constraints}
    assert "range" in ops and "<=" in ops
    le = next(c for c in q.numeric_constraints if c.operator == "<=")
    assert le.normalized_unit == "mg/L" and abs(le.normalized_value - 1000) < 1e-6
    assert q.query_type == "literature_review"


def test_nickel_query() -> None:
    q = parse_query(Q_NICKEL)
    ids = {e.id for e in q.entities}
    assert {"catholyte", "electrowinning", "nickel", "flow_velocity"} <= ids
    assert q.practice_types == ["foreign"]


def test_pgm_query() -> None:
    q = parse_query(Q_PGM)
    ids = {e.id for e in q.entities}
    assert {"gold", "silver", "pgm", "slag"} <= ids
    assert q.last_n_years == 5


def test_injection_query() -> None:
    q = parse_query(Q_INJECTION)
    ids = {e.id for e in q.entities}
    assert "water_injection" in ids or "mine_water" in ids
    assert set(q.practice_types) == {"russia", "foreign"}
    assert q.is_comparison


def test_loose_match_no_false_positive() -> None:
    # шлак (slag) must not match шлам (sludge); никель must still match никелевая
    from kg_extractors.query_parser import _loose_match

    assert not _loose_match("шлак", "шлам")
    assert _loose_match("никель", "никелевая")
    assert _loose_match("шлак", "шлаком")
    assert not _loose_match("вода", "беда")


def test_resolver_fuzzy() -> None:
    r = get_resolver()
    # slight misspelling / variant still resolves
    res = r.resolve("электроэкстракции")
    assert res.entry is not None and res.entry.id == "electrowinning"
    res2 = r.resolve("reverse osmosis")
    assert res2.entry is not None and res2.entry.id == "reverse_osmosis"
