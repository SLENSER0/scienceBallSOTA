"""Domain seed graph (§3.17 / §24.2): a small but representative, evidence-first
knowledge graph covering the six acceptance scenarios. Idempotent (deterministic
IDs + MERGE) so it doubles as an upsert smoke test.
"""

from __future__ import annotations

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore

SCHEMA_VERSION = "0.1.0"
RUN_ID = "run:seed-0001"


def _prov(**extra: object) -> dict:
    base = {
        "extractor_run_id": RUN_ID,
        "schema_version": SCHEMA_VERSION,
        "created_at": "2026-07-02T00:00:00Z",
        "review_status": "accepted",
        "verified": True,
    }
    base.update(extra)
    return base


def build_seed_graph(store: KuzuGraphStore) -> dict[str, int]:
    """Build/refresh the demo graph. Returns node/rel counts."""
    n = store.upsert_node
    e = store.upsert_edge

    # provenance run
    n(RUN_ID, "ExtractorRun", name="seed", **_prov())

    def paper(pid: str, title: str, year: int, geo: str, strength: str, country: str) -> str:
        nid = make_id("Paper", pid)
        n(
            nid,
            "Paper",
            name=title,
            canonical_name=title,
            year=year,
            practice_type=geo,
            evidence_strength=strength,
            country=country,
            **_prov(),
        )
        return nid

    def evidence(eid: str, text: str, doc: str, page: int, strength: str) -> str:
        nid = make_id("Evidence", f"{doc}:{eid}")
        n(
            nid,
            "Evidence",
            text=text,
            doc_id=doc,
            page=page,
            source_type="paragraph",
            evidence_strength=strength,
            confidence=0.9,
            **_prov(),
        )
        return nid

    # =====================================================================
    # 1) Water desalination for a concentrator (SO4/Cl/Ca/Mg/Na, TDS ≤1000)
    # =====================================================================
    water = make_id("Material", "mine water concentrator feed")
    n(
        water,
        "Material",
        name="Оборотная вода обогатительной фабрики",
        canonical_name="mine water",
        material_class="water",
        aliases_text="mine water|process water|оборотная вода|шахтная вода",
        domain="water_treatment",
        **_prov(),
    )
    for ion, val in [
        ("сульфаты SO4", 280),
        ("хлориды Cl", 240),
        ("Ca", 220),
        ("Mg", 210),
        ("Na", 260),
    ]:
        mid = make_id("Measurement", f"water {ion}")
        n(
            mid,
            "Measurement",
            name=f"{ion} концентрация",
            property_name="concentration",
            value_normalized=float(val),
            normalized_unit="mg/L",
            domain="water_treatment",
            confidence=0.9,
            **_prov(),
        )
        e(mid, water, "ABOUT_MATERIAL", confidence=0.9)
    tds = make_id("Measurement", "water tds target")
    n(
        tds,
        "Measurement",
        name="целевой сухой остаток (TDS)",
        property_name="total_dissolved_solids",
        value_normalized=1000.0,
        normalized_unit="mg/L",
        polarity="target",
        **_prov(),
    )
    e(tds, water, "ABOUT_MATERIAL", confidence=0.9)

    ro = make_id("TechnologySolution", "reverse osmosis desalination")
    n(
        ro,
        "TechnologySolution",
        name="Обратный осмос (RO)",
        canonical_name="reverse osmosis",
        aliases_text="reverse osmosis|обратный осмос|RO",
        operation="reverse_osmosis",
        domain="water_treatment",
        practice_type="global",
        **_prov(),
    )
    ie = make_id("TechnologySolution", "ion exchange desalination")
    n(
        ie,
        "TechnologySolution",
        name="Ионный обмен",
        canonical_name="ion exchange",
        aliases_text="ion exchange|ионный обмен",
        operation="ion_exchange",
        domain="water_treatment",
        practice_type="global",
        **_prov(),
    )
    ed = make_id("TechnologySolution", "electrodialysis desalination")
    n(
        ed,
        "TechnologySolution",
        name="Электродиализ",
        canonical_name="electrodialysis",
        aliases_text="electrodialysis|электродиализ",
        operation="electrodialysis",
        domain="water_treatment",
        practice_type="foreign",
        **_prov(),
    )
    p_water = paper(
        "desal-review-2022",
        "Обзор методов обессоливания шахтных вод",
        2022,
        "russia",
        "peer_reviewed",
        "russia",
    )
    ev_water = evidence(
        "ro-removal",
        "RO обеспечивает снижение TDS до <500 мг/л при удалении сульфатов >95%",
        "desal-review-2022.pdf",
        12,
        "peer_reviewed",
    )
    for sol, rem in [(ro, 0.97), (ie, 0.9), (ed, 0.88)]:
        e(sol, water, "TREATS_WATER", confidence=0.85, evidence_ids=[ev_water])
        e(sol, water, "REMOVES_CONTAMINANT", confidence=rem, evidence_ids=[ev_water])
        e(sol, p_water, "SUPPORTED_BY", confidence=0.9, evidence_ids=[ev_water])
    ac_ro = make_id("ApplicabilityCondition", "ro high tds concentrator")
    n(
        ac_ro,
        "ApplicabilityCondition",
        name="Подходит для TDS 1–35 г/л, требует предочистки",
        domain="water_treatment",
        **_prov(),
    )
    e(ro, ac_ro, "HAS_APPLICABILITY_CONDITION", confidence=0.9)

    # =====================================================================
    # 2) Nickel electrowinning — catholyte circulation
    # =====================================================================
    ni = make_id("Material", "nickel")
    n(
        ni,
        "Material",
        name="Никель",
        canonical_name="nickel",
        material_class="metal",
        aliases_text="nickel|никель|Ni",
        domain="electrometallurgy",
        **_prov(),
    )
    catholyte = make_id("Material", "catholyte nickel")
    n(
        catholyte,
        "Material",
        name="Католит",
        canonical_name="catholyte",
        material_class="electrolyte",
        aliases_text="catholyte|католит",
        domain="electrometallurgy",
        **_prov(),
    )
    cell = make_id("Equipment", "diaphragm electrowinning cell")
    n(
        cell,
        "Equipment",
        name="Диафрагменная ванна электроэкстракции",
        canonical_name="diaphragm cell",
        aliases_text="diaphragm cell|диафрагменная ячейка",
        domain="electrometallurgy",
        **_prov(),
    )
    ew = make_id("TechnologySolution", "catholyte circulation scheme")
    n(
        ew,
        "TechnologySolution",
        name="Схема циркуляции католита через ванну",
        canonical_name="catholyte circulation",
        operation="electrowinning",
        aliases_text="catholyte circulation|циркуляция католита",
        domain="electrometallurgy",
        practice_type="global",
        **_prov(),
    )
    fv = make_id("Measurement", "catholyte flow velocity optimal")
    n(
        fv,
        "Measurement",
        name="Оптимальная скорость циркуляции католита",
        property_name="flow_velocity",
        value_normalized=0.2,
        normalized_unit="m/s",
        value_raw="0.1–0.3 м/с",
        domain="electrometallurgy",
        confidence=0.8,
        **_prov(),
    )
    cd = make_id("Measurement", "nickel current density")
    n(
        cd,
        "Measurement",
        name="Плотность тока",
        property_name="current_density",
        value_normalized=250.0,
        normalized_unit="A/m2",
        domain="electrometallurgy",
        confidence=0.85,
        **_prov(),
    )
    p_ni = paper(
        "ni-ew-2021",
        "Электроэкстракция никеля: влияние состава электролита",
        2021,
        "russia",
        "internal_report",
        "russia",
    )
    ev_ni = evidence(
        "flow",
        "оптимальная скорость циркуляции католита 0.1–0.3 м/с "
        "обеспечивает равномерное качество катода",
        "ni-ew-2021.pdf",
        8,
        "internal_report",
    )
    e(ew, catholyte, "CIRCULATES_ELECTROLYTE", confidence=0.85, evidence_ids=[ev_ni])
    e(cell, cell, "FEEDS_ELECTROLYTE_TO_CELL", confidence=0.7)
    e(fv, ew, "ABOUT_REGIME", confidence=0.8, evidence_ids=[ev_ni])
    e(cd, ew, "ABOUT_REGIME", confidence=0.85)
    e(ew, ni, "APPLIES_TO", confidence=0.8)
    e(fv, p_ni, "SUPPORTED_BY", confidence=0.85, evidence_ids=[ev_ni])
    # contradiction: a foreign source claims 0.5 m/s
    fv2 = make_id("Measurement", "catholyte flow velocity foreign")
    n(
        fv2,
        "Measurement",
        name="Скорость циркуляции католита (заруб.)",
        property_name="flow_velocity",
        value_normalized=0.5,
        normalized_unit="m/s",
        practice_type="foreign",
        confidence=0.7,
        **_prov(),
    )
    e(fv2, ew, "ABOUT_REGIME", confidence=0.7)
    contra = make_id("Contradiction", "catholyte velocity conflict")
    n(
        contra,
        "Contradiction",
        name="Разные значения оптимальной скорости циркуляции католита",
        gap_type="contradictory_measurements",
        **_prov(),
    )
    e(fv, fv2, "CONTRADICTS", confidence=0.8)
    e(contra, ew, "ABOUT", confidence=0.9)

    # =====================================================================
    # 3) Precious metals (Au/Ag/PGM) partitioning matte vs slag
    # =====================================================================
    cu_matte = make_id("Material", "copper matte")
    n(
        cu_matte,
        "Material",
        name="Медный штейн",
        canonical_name="copper matte",
        material_class="matte",
        aliases_text="copper matte|медный штейн|Cu matte",
        domain="pyrometallurgy",
        **_prov(),
    )
    slag = make_id("Material", "smelter slag")
    n(
        slag,
        "Material",
        name="Шлак",
        canonical_name="slag",
        material_class="slag",
        aliases_text="slag|шлак",
        domain="pyrometallurgy",
        **_prov(),
    )
    p_pgm_id = paper("pgm-2023", "Распределение Au, Ag и МПГ между штейном и шлаком",
                     2023, "russia", "peer_reviewed", "russia")
    ev_pgm = evidence("pgm-dc", "коэффициент распределения МПГ штейн/шлак достигает 0.98",
                      "pgm-2023.pdf", 5, "peer_reviewed")
    for metal, dc in [("Au золото", 0.95), ("Ag серебро", 0.9), ("МПГ PGM", 0.98)]:
        m = make_id("Measurement", f"partition {metal}")
        n(
            m,
            "Measurement",
            name=f"Коэффициент распределения {metal} штейн/шлак",
            property_name="distribution_coefficient",
            value_normalized=dc,
            normalized_unit="ratio",
            domain="pyrometallurgy",
            confidence=0.8,
            **_prov(),
        )
        e(m, cu_matte, "DISTRIBUTES_BETWEEN", confidence=0.8)
        e(m, slag, "DISTRIBUTES_BETWEEN", confidence=0.8)
        e(m, p_pgm_id, "SUPPORTED_BY", confidence=0.8, evidence_ids=[ev_pgm])
    e(cu_matte, slag, "PARTITIONED_TO_PHASE", confidence=0.8)

    # =====================================================================
    # 4) Mine water deep injection — Russia vs foreign
    # =====================================================================
    inj_ru = make_id("TechnologySolution", "deep well injection russia")
    n(
        inj_ru,
        "TechnologySolution",
        name="Закачка шахтных вод в глубокие горизонты (РФ)",
        canonical_name="deep well injection",
        operation="water_injection",
        aliases_text="deep well injection|закачка в глубокие горизонты",
        domain="environment",
        practice_type="russia",
        country="russia",
        **_prov(),
    )
    inj_ca = make_id("TechnologySolution", "deep well injection canada")
    n(
        inj_ca,
        "TechnologySolution",
        name="Deep well injection (Canada)",
        canonical_name="deep well injection foreign",
        operation="water_injection",
        domain="environment",
        practice_type="foreign",
        country="canada",
        **_prov(),
    )
    well = make_id("Facility", "deep injection well")
    n(
        well,
        "Facility",
        name="Нагнетательная скважина",
        canonical_name="injection well",
        country="russia",
        **_prov(),
    )
    capex = make_id("TechnoEconomicIndicator", "injection capex ru")
    n(
        capex,
        "TechnoEconomicIndicator",
        name="CAPEX закачки",
        property_name="capex",
        value_normalized=5.0,
        normalized_unit="MUSD",
        country="russia",
        **_prov(),
    )
    e(inj_ru, well, "INJECTS_INTO_HORIZON", confidence=0.8)
    e(inj_ru, capex, "HAS_TECHNOECONOMIC_INDICATOR", confidence=0.7)
    e(inj_ru, inj_ca, "COMPARES_WITH", confidence=0.6)
    p_inj = paper("injection-2020", "Практика закачки шахтных вод в России и за рубежом",
                  2020, "russia", "internal_report", "russia")
    ev_inj = evidence("inj-capex", "CAPEX закачки шахтных вод в глубокие горизонты ~5 млн USD; "
                      "практика применялась в России и в Канаде",
                      "injection-2020.pdf", 3, "internal_report")
    e(inj_ru, p_inj, "SUPPORTED_BY", confidence=0.8, evidence_ids=[ev_inj])
    e(inj_ca, p_inj, "SUPPORTED_BY", confidence=0.7, evidence_ids=[ev_inj])
    e(capex, ev_inj, "SUPPORTED_BY", confidence=0.8, evidence_ids=[ev_inj])

    # =====================================================================
    # 5) SO2 removal / gas cleaning
    # =====================================================================
    flue = make_id("Material", "flue gas so2")
    n(
        flue,
        "Material",
        name="Отходящий газ (SO2)",
        canonical_name="flue gas",
        material_class="gas",
        aliases_text="flue gas|отходящий газ|SO2|сернистый газ",
        domain="environment",
        **_prov(),
    )
    scrubber = make_id("TechnologySolution", "wet scrubber so2")
    n(
        scrubber,
        "TechnologySolution",
        name="Мокрая сероочистка (скруббер)",
        canonical_name="wet scrubber",
        operation="so2_removal",
        aliases_text="wet scrubber|скруббер|FGD|limestone scrubbing",
        domain="environment",
        practice_type="global",
        **_prov(),
    )
    reff = make_id("Measurement", "so2 removal efficiency")
    n(
        reff,
        "Measurement",
        name="Эффективность улавливания SO2",
        property_name="removal_efficiency",
        value_normalized=95.0,
        normalized_unit="%",
        domain="environment",
        confidence=0.85,
        **_prov(),
    )
    e(scrubber, flue, "REMOVES_CONTAMINANT", confidence=0.9)
    e(reff, scrubber, "ABOUT_REGIME", confidence=0.85)
    paper(
        "so2-2019",
        "Обзор методов удаления SO2 из отходящих газов",
        2019,
        "global",
        "peer_reviewed",
        "finland",
    )

    # =====================================================================
    # 6) Cold-climate heap leaching — knowledge GAP example
    # =====================================================================
    heap = make_id("ProcessingRegime", "cold climate heap leaching nickel")
    n(
        heap,
        "ProcessingRegime",
        name="Кучное выщелачивание в холодном климате",
        canonical_name="cold climate heap leaching",
        operation="heap_leaching",
        climate_zone="cold",
        domain="hydrometallurgy",
        **_prov(),
    )
    gap = make_id("Gap", "cold heap leaching nickel gap")
    n(
        gap,
        "Gap",
        name="Нет экспериментов: холодный климат + кучное выщелачивание + никелевая руда",
        gap_type="low_coverage_material",
        domain="hydrometallurgy",
        review_status="pending",
        verified=False,
        extractor_run_id=RUN_ID,
        schema_version=SCHEMA_VERSION,
        created_at="2026-07-02T00:00:00Z",
    )
    e(gap, heap, "ABOUT_REGIME", confidence=0.9)
    e(heap, ni, "APPLIES_TO", confidence=0.6)

    # Experts / labs
    lab = make_id("Lab", "hydrometallurgy lab")
    n(
        lab,
        "Lab",
        name="Лаборатория гидрометаллургии",
        country="russia",
        domain="hydrometallurgy",
        **_prov(),
    )
    person = make_id("Person", "expert ivanov")
    n(
        person,
        "Person",
        name="Иванов И.И.",
        canonical_name="ivanov",
        confidentiality_level="internal",
        **_prov(),
    )
    e(person, lab, "MEMBER_OF", confidence=1.0)
    e(person, ew, "EXPERT_IN", confidence=0.9)
    e(lab, ew, "EXPERT_IN", confidence=0.8)

    return store.counts()


def main() -> None:
    from kg_common import get_settings

    s = get_settings()
    s.ensure_runtime_dirs()
    store = KuzuGraphStore(s.kuzu_db_path)
    counts = build_seed_graph(store)
    print(f"seed graph: {counts}")
    print("by label:", store.counts_by_label())
    store.close()


if __name__ == "__main__":
    main()
