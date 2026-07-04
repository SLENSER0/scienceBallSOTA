// Backend contract types (§5.3). Kept in parity with kg_common.dto (camelCase).

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  confidence?: number | null;
  evidenceCount?: number | null;
  verified?: boolean | null;
  missingFields?: string[] | null;
  properties?: Record<string, unknown> | null;
  communityId?: number | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
  confidence?: number | null;
  evidenceCount?: number | null;
  inferred?: boolean | null;
  contradicted?: boolean | null;
  evidenceIds?: string[] | null;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface EvidenceContext {
  evidence_id: string;
  span: string;
  chunk_text: string;
  highlight_offset: number;
  highlight_len: number;
  doc_id?: string | null;
  doc_title?: string | null;
  page?: number | null;
  practice_type?: string | null;
  country?: string | null;
  year?: number | null;
  evidence_strength?: string | null;
  confidence?: number | null;
}

export interface EvidenceRef {
  evidenceId: string;
  sourceId: string;
  docId?: string | null;
  page?: number | null;
  text?: string | null;
  confidence: number;
  evidenceStrength?: string | null;
}

export interface Citation {
  marker: string;
  evidence: EvidenceRef;
  sourceTitle?: string | null;
  year?: number | null;
  geography?: string | null;
  asOf?: string | null; // date of actualization (source ingest date)
}

export interface AnswerTable {
  columns: string[];
  rows: Record<string, string>[];
}

export interface AnswerPayload {
  answerMarkdown: string;
  citations: Citation[];
  graph?: GraphResponse | null;
  table?: AnswerTable | null;
  gaps: { name?: string; type?: string }[];
  contradictions: { name?: string }[];
  confidence?: number | null;
  parsedQuery?: Record<string, unknown> | null;
  usedModels: string[];
  reasoning?: string;
}

export interface CoverageDomain {
  domain: string;
  sources: number;
  technologies: number;
  measurements: number;
  gaps: number;
  contradictions: number;
  risk: string;
}

export interface GlossaryTerm {
  id: string;
  type: string;
  canonical_ru: string;
  canonical_en: string;
  aliases: string[];
  domain?: string | null;
}

export interface NodeRow {
  id: string;
  type: string;
  name: string;
  domain?: string | null;
}

export interface LineageRun {
  run_id: string;
  type: string;
  name: string;
  created_at: string;
  produced_edges: number;
  by_label: Record<string, number>;
}

export interface AuditEntry {
  ts: number;
  user: string;
  role: string;
  action: string;
  detail?: Record<string, unknown> | null;
}

export interface SavedView {
  view_id: string;
  name: string;
  kind: string;
  payload: Record<string, unknown>;
}

export interface AdvisorCandidate {
  id: string;
  name: string;
  practice_type: string;
  fit_score: number;
  verdict: string;
  supports: string[];
  limitations: string[];
  gaps: string[];
  n_measurements: number;
  relevance: number; // 2=on-topic, 1=same domain, 0=off-topic
  model?: string | null;
}

export interface AdvisorResult {
  query: string;
  geography?: string | null;
  constraints: Record<string, unknown>[];
  candidates: AdvisorCandidate[];
  summary: string;
  contradictions: Record<string, unknown>[];
  usedModels: string[];
}

export interface ContradictionSummary {
  id: string;
  name: string;
  status?: string | null;
  values: number[];
  unit?: string | null;
  material?: string | null;
  spread: number;
}

export interface ContradictionSide {
  value: number | null;
  unit: string | null;
  property: string | null;
  practice: string | null;
  year: number | null;
  country: string | null;
  evidence: string | null;
}

export interface ContradictionAnalysis {
  id: string;
  name: string;
  verdict: string;
  explanation: string;
  sides: ContradictionSide[];
  recommendation: string;
  model?: string | null;
}

export interface DomainCoverageRow {
  domain: string;
  sources: number;
  measurements: number;
  gaps: number;
  contradictions: number;
  risk: string;
}

export interface KnowledgeSnapshot {
  counts: { nodes: number; rels: number };
  byLabel: Record<string, number>;
  coverage: { by_domain: DomainCoverageRow[]; risk_domains: string[]; totals: Record<string, number> };
  gaps: { name: string; type?: string; domain?: string }[];
  contradictions: ContradictionSummary[];
  topTechnologies: { id: string; name: string; degree: number }[];
}

export interface Briefing {
  snapshot: KnowledgeSnapshot;
  briefing: string;
  model?: string | null;
}

export interface PrioritizedGap {
  id: string;
  name: string;
  type?: string | null;
  domain?: string | null;
  priority: number;
  impact: number;
  feasibility: number;
  rationale: string;
  action: string;
  scored: boolean;
  model?: string | null;
}

// -- §17.9 GraphRAG community summaries -------------------------------------
export interface CommunitySummary {
  community_id: number;
  title: string;
  summary: string;
  size: number;
  domains: string[];
  top_entities: string[];
  member_ids: string[];
}

// -- §8.8 Entity-resolution candidate review -------------------------------
export interface ERMention {
  id: string;
  name: string | null;
  label: string | null;
  formula: string | null;
  review_status: string | null;
}
export interface ERCandidate {
  candidate_id: string;
  entity_type: string;
  decision: string; // auto_merge | review_needed | separate
  match_probability: number;
  canonical_id: string;
  blocked_by_review: boolean;
  mentions: ERMention[];
}
export interface ERCandidatesResponse {
  status: string;
  entity_type: string;
  count: number;
  candidates: ERCandidate[];
}

// -- §3.14 similarity / implicit-link suggestions --------------------------
export interface SimLinkSeed {
  id: string;
  name: string | null;
  label: string | null;
}
export interface SimLinksSeeds {
  count: number;
  seeds: SimLinkSeed[];
}
export interface SimLinkSupporter {
  id: string;
  name: string;
  similarity: number;
}
export interface SimLinkSuggestion {
  target: string;
  target_name: string | null;
  target_label: string;
  raw_score: number;
  score: number;
  support_count: number;
  supporters: SimLinkSupporter[];
  reason: string;
}
export interface SimLinksSuggest {
  seed: { id: string; name: string | null; label: string | null };
  method: 'gds' | 'in_process';
  target_label: string | null;
  count: number;
  suggestions: SimLinkSuggestion[];
}

// -- §8.2 Materials Project authority badge --------------------------------
export interface MaterialsProjectBadgeData {
  entity_id: string;
  has_authority: boolean;
  source_system: string;
  mp_id: string | null;
  canonical_formula: string | null;
  url: string | null;
}
