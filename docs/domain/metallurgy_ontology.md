# Доменная онтология: горно-металлургия (§24.2)

Онтология реализована как **generic property graph** (ADR-0001): один тип узла
`Node` с типизированными колонками + JSON `props`, и один тип ребра `Rel` с полем
`type`. Доменные подтипы моделируются не отдельными labels, а **enum-значениями**
(`material_class`, `operation`, `property_name`, `practice_type`, `domain`),
что даёт расширяемость без миграций схемы. LinkML-источник:
`packages/kg_schema/src/kg_schema/linkml/kg_ontology.yaml`; Pydantic/enum-модели:
`packages/kg_schema/src/kg_schema/{labels,relationships,enums}.py`.

## Поток знаний

```
Material ──HAS_COMPOSITION──▶ Composition ──CONTAINS_ELEMENT──▶ ChemicalElement
   │
   └──(ABOUT_MATERIAL)──◀ Measurement ──OF_PROPERTY──▶ Property
                            │  │
        ProcessingRegime ───┘  └──SUPPORTED_BY──▶ Evidence ◀──(doc_id)── Paper
        │  ├─HAS_PARAMETER──▶ Parameter
        │  └─USED_EQUIPMENT──▶ Equipment
   TechnologySolution ─APPLIES_TO─▶ ProcessingRegime
        ├─TREATS_WATER / REMOVES_CONTAMINANT ─▶ Material(water)
        ├─HAS_TECHNOECONOMIC_INDICATOR ─▶ TechnoEconomicIndicator (CAPEX/OPEX/NPV)
        ├─HAS_APPLICABILITY_CONDITION ─▶ ApplicabilityCondition
        ├─HAS_LIMITATION ─▶ Limitation
        ├─HAS_PRACTICE_TYPE / IMPLEMENTED_IN_COUNTRY ─▶ Geography/Country
        └─COMPARES_WITH ─▶ TechnologySolution
   Recommendation ─RECOMMENDS_SOLUTION─▶ TechnologySolution
   Gap ─ABOUT─▶ Entity     Contradiction ─ABOUT─▶ Entity
```

## Классы (labels + material_class / operation subtypes)

| Группа | Реализация |
|---|---|
| Материалы/потоки | `Material` + `MaterialClass`: ore, ore_body, deposit, concentrate, matte, slag, tailings, metal, alloy, solution, electrolyte, **catholyte, anolyte**, leach_solution, pregnant_leach_solution, raffinate, gas, flue_gas, water, mine_water, process_water, waste, technogenic_gypsum, coal_waste, reagent |
| Процессы | `ProcessingRegime` + `ProcessingOperation`: leaching, heap_leaching, bioleaching, flotation, electrowinning, electrorefining, flash_smelting, fluidized_bed, smelting, converting, roasting, desalination, reverse_osmosis, ion_exchange, electrodialysis, nanofiltration, lime_softening, gas_cleaning, so2_removal, water_injection, aging, annealing |
| Решения | `TechnologySolution`, `TechnologyComparison` (схемы/flow-sheets как `operation` + `props`) |
| Оборудование | `Equipment` (+ `equipment_class`: furnace, cell, pump, unit, well, thickener, filter_press…) |
| Параметры/свойства | `Property` + `Measurement` + `PropertyClass`: concentration, temperature, flow, electrochemical, mechanical, recovery, efficiency, economic, energy, physicochemical |
| Контекст | `Geography`, `Country`, `Facility`, `PracticeType` (`PracticeGeography`: russia/cis/foreign/global/unknown) |
| Knowledge-output | `Recommendation`, `Limitation`, `ApplicabilityCondition`, `Gap`, `Contradiction`, `TechnologyComparison`, `KnowledgeClaim` |

## Enums (§24.2)

- **MetallurgicalDomain**: hydrometallurgy, pyrometallurgy, environment, water_treatment, waste_processing, mineral_processing, electrometallurgy.
- **PracticeGeography**: russia, cis, foreign, global, unknown.
- **EvidenceStrength**: peer_reviewed, patent, standard, experiment_protocol, internal_report, expert_comment, unverified.

## Доменные связи

`treats_water`, `removes_contaminant`, `injects_into_horizon`,
`circulates_electrolyte`, `feeds_electrolyte_to_cell`, `operates_in_climate`,
`implemented_in_country`, `has_technoeconomic_indicator`,
`has_applicability_condition`, `has_limitation`, `recommends_solution`,
`compares_with`, `has_practice_type`; распределение металлов:
`distributes_between`, `partitioned_to_phase`, `has_distribution_coefficient`.

Полный каталог рёбер — `EDGE_SCHEMA` в `relationships.py`; проверяется через
`GET /api/v1/graph/schema`.

## Seed-примеры (по одному на сценарий, §3.17)

1. **Водоподготовка** — обратный осмос / ионный обмен / электродиализ для оборотной воды (SO₄/Cl/Ca/Mg/Na, TDS ≤ 1000 мг/л).
2. **Электроэкстракция никеля** — циркуляция католита (flow_velocity, противоречие отеч./зарубеж.).
3. **Нагнетание шахтных вод** — закачка в глубокие горизонты (Россия vs Канада, CAPEX).
4. **Газоочистка SO₂** — мокрая сероочистка, removal_efficiency 95 %.
5. **Кучное выщелачивание в холодном климате** — пример data-gap.
6. **Взвешенная плавка (ПВП)** — распределение Cu штейн/шлак, L(Cu) ≈ 25 (`distributes_between`, `partitioned_to_phase`).

Схема валидируется (`import kg_schema` + enum-checks), все labels/relationships
доступны через `/api/v1/graph/schema`, seed идемпотентен.
