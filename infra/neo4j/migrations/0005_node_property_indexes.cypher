// HAND-AUTHORED — property indexes for the generic :Node model (server profile).
//
// Neo4jGraphStore (kg_retrievers/neo4j_store.py) writes EVERY node under a single
// :Node label with the domain type carried in the `label` PROPERTY, not as a Neo4j
// label. The typed-label indexes in 0002_indexes.cypher / 0003_fulltext.cypher
// (:Measurement, :Gap, :Paper, :ProcessingRegime, :TechnologySolution, :Evidence…)
// therefore never match a stored node and never accelerate a query.
//
// These indexes cover the properties actually filtered/ordered on :Node by the
// wired API routers and retrievers under RUNTIME_PROFILE=server:
//   n.label        — similarity_links/seeds, missing_links, link_prediction,
//                     community/coverage/expert retrievers, agent tools (WHERE n.label = $x)
//   n.community_id — community_cluster_graph, community_panel, corpus_overview,
//                     search, community.py/community_hierarchy (WHERE n.community_id = $c)
//   n.doc_id       — tools_ext, pipeline_orchestrator (WHERE n.doc_id = $d)
//   n.confidence   — demo_run, facet_search (ORDER BY), gap_analysis, curation (WHERE/ORDER)
CREATE INDEX node_label_index IF NOT EXISTS FOR (n:Node) ON (n.label);
CREATE INDEX node_community_id_index IF NOT EXISTS FOR (n:Node) ON (n.community_id);
CREATE INDEX node_doc_id_index IF NOT EXISTS FOR (n:Node) ON (n.doc_id);
CREATE INDEX node_confidence_index IF NOT EXISTS FOR (n:Node) ON (n.confidence);
