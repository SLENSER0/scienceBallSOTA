# FAIR, standards & interoperability (§24.19)

## FAIR principles

- **Findable** — every Document, Experiment, fact, Evidence and Recommendation
  has a stable deterministic ID (`kg_common.ids`) and machine-readable metadata
  (doc_type, year, country, practice_type, evidence_strength, review_status).
  Full-text + vector + graph search make them findable in RU & EN.
- **Accessible** — REST API (`/api/v1/...`), JSON-LD/Markdown/JSON export, OpenAPI
  schema at `/openapi.json`, `/api/v1/graph/schema`. RBAC governs access.
- **Interoperable** — the LinkML ontology (`kg_ontology.yaml`), JSON-LD context on
  exports (`/export?format=jsonld`), and SHACL shapes (`resources/shapes.ttl`)
  provide an OWL/RDF interoperability layer over the operational property graph.
- **Reusable** — provenance (extractor_run_id, schema_version, confidence), source
  license / usage_rights / access_policy metadata, evidence-first facts.

## Boundary: property graph vs RDF

The **operational** store is a property graph (Kuzu/Neo4j) for fast multi-hop +
numeric queries. **RDF/OWL/SHACL/JSON-LD are the interoperability/export layer**
only — we deliberately do not build a SPARQL-first stack (ADR-0003, §24.21).

## Standards / regulations

`Standard`/`Regulation` source types carry `jurisdiction`, `effective_date`,
`status`. Obsolete standards/patents (past `valid_until`) are flagged
`needs_update` and excluded from recommendations without a warning (§24.7).

## SHACL critical constraints (`resources/shapes.ttl`)

- Measurement must have a unit (else `missing_unit` gap).
- Recommendation must reference ≥1 Evidence.
- TechnologySolution must have an applicability condition.
- Practice claim must state geography.
- Evidence must have a source span (doc_id + text).

## JSON-LD export

`POST /api/v1/export {format:"jsonld"}` emits the answer subgraph with a domain
`@context`; restricted evidence is excluded for unauthorized roles.
