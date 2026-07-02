# Graph model

Source of truth: `packages/kg_schema` (labels, relationships, enums). The LinkML
ontology (`packages/kg_schema/src/kg_schema/linkml/kg_ontology.yaml`) and Neo4j
migrations (`infra/neo4j/migrations/`) are **generated** from it by
`make schema-gen` (§3.2/§3.3/§3.10-3.13).

## Labels (§8.1)

33 core labels + domain labels (§24.2): Document, Paper, Section, Paragraph,
Table, Figure, Chunk, Evidence, Claim, Finding, Experiment, Sample, Material,
Alloy, ChemicalElement, Composition, ProcessingRegime, ProcessingStep,
Parameter, Equipment, Lab, ResearchTeam, Person, Property, Measurement, Unit,
Method, Dataset, Project, Decision, CurationEvent, Gap, Contradiction — plus
Geography, Country, Facility, TechnologySolution, Recommendation, Limitation,
ApplicabilityCondition, TechnologyComparison, KnowledgeClaim, Standard,
TechnoEconomicIndicator. Provenance run nodes: ExtractorRun, GapScanRun.

Super-label **`:Entity`** = resolvable/embeddable entities (Material, Property,
Equipment, Lab, Person, ResearchTeam, ProcessingRegime, Method, ChemicalElement,
TechnologySolution, Recommendation, Facility, Geography).

## Relationships (§8.2)

`RelType` + `EDGE_SCHEMA` declare `(from, rel, to)` signatures; `is_valid_edge`
rejects undeclared edges. Domain relations (§24.2): TREATS_WATER,
REMOVES_CONTAMINANT, CIRCULATES_ELECTROLYTE, DISTRIBUTES_BETWEEN,
IMPLEMENTED_IN_COUNTRY, HAS_PRACTICE_TYPE, HAS_TECHNOECONOMIC_INDICATOR, …

## Evidence-first (§8.3 / §3.6)

Every factual node (Measurement, Claim, Finding, Recommendation, Contradiction)
must be `SUPPORTED_BY` an `Evidence` node carrying a source span (doc_id + page +
text). "No source span → no graph fact" is enforced in the extraction schema
(`kg_schema.extraction`, non-empty `evidence_text`).

## Provenance / versioning (§3.7)

Factual nodes/edges carry `confidence`, `extractor_run_id`, `schema_version`,
`created_at`, `review_status`. Reviewed fields (`accepted`/`corrected`) are
protected from re-ingestion overwrite (`upsert_node_guarded`). Curation records
`CurationEvent(before/after/actor/reason)` linked via `CHANGED`.

## Embedded storage (Kuzu)

The heterogeneous graph is stored in one generic `Node` table (typed columns for
the numeric/geo/time/review filters + a JSON `props` catch-all) and one generic
`Rel` table (typed provenance). Deterministic IDs (`kg_common.ids`) + MERGE make
upserts idempotent. Server profile maps the same model onto Neo4j (see
`infra/neo4j/migrations/`). See ADR-0005.

## Deterministic IDs (§3.8)

`<prefix>:<slug|hash>` — `material:al-cu-2024`, `property:hardness`,
`regime:<hash>`, `ev:<uuid5>`. `canonical_key()` normalizes (NFKC, lowercase,
collapse separators) so surface variants resolve to one id.
