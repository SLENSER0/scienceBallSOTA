# OSS reference catalog (§1.14 / §21)

`status`: **core** = cloned for direct study; **reference** = design reference;
**benchmark** = evaluated alternative; **optional** = future/nice-to-have.
All are OSS-licensed (permitted by §7.5).

## Agent / RAG / extraction

| Repo | URL | Plan | status |
|---|---|---|---|
| LangGraph | https://github.com/langchain-ai/langgraph | agent-service §13 | core |
| LlamaIndex | https://github.com/run-llama/llama_index | kg_extractors/retrievers §9/§10 | reference |
| Microsoft GraphRAG | https://github.com/microsoft/graphrag | retrieval Mode C §11 | reference |
| Neo4j LLM Graph Builder | https://github.com/neo4j-labs/llm-graph-builder | schema patterns §3 | core |
| Haystack | https://github.com/deepset-ai/haystack | retrieval §12 | reference |
| GLiNER | https://github.com/urchade/GLiNER | NER §6 | core |

## Ingestion

| Repo | URL | Plan | status |
|---|---|---|---|
| Docling | https://github.com/docling-project/docling | ingestion §5 | reference |
| Docling Serve | https://github.com/docling-project/docling-serve | ingestion §5 | reference |
| Marker | https://github.com/datalab-to/marker | ingestion §5 | benchmark |
| Unstructured | https://github.com/Unstructured-IO/unstructured | ingestion §5 | benchmark |

## Graph / search DBs

| Repo | URL | Plan | status |
|---|---|---|---|
| Neo4j | https://github.com/neo4j/neo4j | graph §3 | reference |
| APOC | https://github.com/neo4j-contrib/neo4j-apoc-procedures | graph §3.9 | reference |
| GDS | https://github.com/neo4j/graph-data-science | graph §3.14 | reference |
| Kuzu | https://github.com/kuzudb/kuzu | graph (embedded) §3 | core |
| Qdrant | https://github.com/qdrant/qdrant | vector §4 | reference |
| OpenSearch | https://github.com/opensearch-project/OpenSearch | keyword §4 | reference |
| ArangoDB / Memgraph / TypeDB | .../arangodb · .../memgraph · .../typedb | alt graph §22 | reference |
| Amazon Neptune / JanusGraph | managed · https://github.com/JanusGraph/janusgraph | portability §24.21 | reference |

## Graph UI

| Repo | URL | Plan | status |
|---|---|---|---|
| Reagraph | https://github.com/reaviz/reagraph | frontend §17 | core |
| Cytoscape.js / Sigma.js / Graphology | .../cytoscape.js · .../sigma.js · .../graphology | frontend §17 | reference |
| react-force-graph / G6 / Graphin / React-Flow | vasturiano · antvis/G6 · antvis/Graphin · xyflow/xyflow | frontend §17 | reference |
| Apache ECharts | https://github.com/apache/echarts | dashboards §17 | core |

## Entity resolution / orchestration / lineage

| Repo | URL | Plan | status |
|---|---|---|---|
| Splink | https://github.com/moj-analytical-services/splink | ER §8 | reference |
| Dedupe / OpenRefine | https://github.com/dedupeio/dedupe · .../OpenRefine | ER §8 | benchmark |
| Dagster | https://github.com/dagster-io/dagster | orchestration §9 | reference |
| DataHub / OpenMetadata / Marquez | datahub-project · open-metadata · MarquezProject | lineage §10 | reference |
| MLflow / DVC / lakeFS / Airbyte / Atlas | mlflow · iterative/dvc · treeverse/lakeFS · airbytehq · apache/atlas | governance §10 | optional |

## Materials data / NLP (RU)

| Repo | URL | Plan | status |
|---|---|---|---|
| MatKG / MatBERT / MatEntityRecognition / Matscholar / Propnet | olivettigroup · lbnlp · CederGroupHub · materialsintelligence | seed vocab §3.2 | reference |
| Materials Project API / pymatgen | materialsproject/api · .../pymatgen | canonical keys §3.8 | reference |
| DeepPavlov / spaCy / ruBERT | https://github.com/deeppavlov/DeepPavlov · https://github.com/explosion/spaCy | RU NLP §24.21 | benchmark |

## Ontology governance / dashboards / labs

| Repo | URL | Plan | status |
|---|---|---|---|
| LinkML / Protégé | https://github.com/linkml/linkml · protegeproject/protege | ontology §3/§8 | reference |
| Superset | https://github.com/apache/superset | dashboards §17 | optional |
| eLabFTW / openBIS | https://github.com/elabftw/elabftw · https://github.com/openbis | lab integ §20 | optional |

## Alternatives & benchmarks (§24.21) — reference/benchmark only

| Repo | URL | Plan | status |
|---|---|---|---|
| Amazon Neptune | managed service (aws.amazon.com/neptune) | graph portability §24.21 | reference |
| JanusGraph | https://github.com/JanusGraph/janusgraph | graph portability §24.21 | reference |
| Vespa | https://github.com/vespa-engine/vespa | search alt §24.21 | benchmark |
| Elasticsearch | https://github.com/elastic/elasticsearch | keyword alt §24.21 | benchmark |
| DeepPavlov | https://github.com/deeppavlov/DeepPavlov | RU NLP §24.21 | benchmark |
| spaCy / spacy-ru | https://github.com/explosion/spaCy | RU sentence/abbr §24.21 | optional |
| ruBERT / DeepPavlov ru-bert | https://huggingface.co/DeepPavlov/rubert-base-cased | RU embeddings §24.21 | optional |
| Marquez | https://github.com/MarquezProject/marquez | OpenLineage §10 | reference |
| Apache Superset | https://github.com/apache/superset | dashboards §17 | optional |
- open_deep_research — https://github.com/langchain-ai/open_deep_research (MIT) — deep-research agent; VENDORED + integrated (real graph runs on OSS LLM via /research/deep)
