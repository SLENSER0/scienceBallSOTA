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
