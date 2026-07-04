import type {
  AdvisorResult,
  AnswerPayload,
  AuditEntry,
  Briefing,
  CommunitySummary,
  ContradictionAnalysis,
  ContradictionSummary,
  CoverageDomain,
  ERCandidatesResponse,
  EvidenceContext,
  GlossaryTerm,
  GraphResponse,
  LineageRun,
  MaterialsProjectBadgeData,
  NodeRow,
  PrioritizedGap,
  SavedView,
  SimLinksSeeds,
  SimLinksSuggest,
} from './types';

function authHeaders(): Record<string, string> {
  try {
    const raw = localStorage.getItem('sb.session');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.token) return { Authorization: `Bearer ${s.token}` };
      if (s?.role) return { 'X-Role': s.role }; // dev fallback: role header
    }
  } catch {
    /* ignore */
  }
  return {};
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface AuthConfig {
  oidc: { enabled: boolean; issuer?: string; client_id?: string; authorize_url?: string; scopes?: string };
  roles: string[];
}

export interface QueryOptions {
  role?: string;
  useLlm?: boolean;
  geography?: string; // russia | cis | foreign | global | all
}

export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
  last_message_at: string;
}

export interface ChatMessage {
  message_id: string;
  role: string;
  content: string;
  created_at: string;
}

export const api = {
  authConfig(): Promise<AuthConfig> {
    return req('/api/v1/auth/config');
  },
  login(username: string, role: string): Promise<{ token: string; role: string }> {
    return req('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, role }),
    });
  },
  query(query: string, opts: QueryOptions = {}): Promise<AnswerPayload> {
    return req<AnswerPayload>('/api/v1/query', {
      method: 'POST',
      body: JSON.stringify({
        query,
        role: opts.role ?? 'researcher',
        use_llm: opts.useLlm ?? true,
        geography: opts.geography && opts.geography !== 'all' ? opts.geography : null,
      }),
    });
  },
  coverage(): Promise<{ domains: CoverageDomain[] }> {
    return req('/api/v1/admin/coverage');
  },
  stats(): Promise<{ counts: { nodes: number; rels: number }; by_label: Record<string, number> }> {
    return req('/api/v1/admin/stats');
  },
  glossary(q = ''): Promise<{ count: number; terms: GlossaryTerm[] }> {
    return req(`/api/v1/domain/glossary?q=${encodeURIComponent(q)}`);
  },
  neighbors(id: string, depth = 1): Promise<GraphResponse> {
    return req(`/api/v1/entities/${encodeURIComponent(id)}/neighbors?depth=${depth}`);
  },
  evidenceContext(id: string): Promise<EvidenceContext> {
    return req(`/api/v1/evidence/${encodeURIComponent(id)}/context`);
  },
  evidence(id: string): Promise<Record<string, unknown>> {
    return req(`/api/v1/evidence/${encodeURIComponent(id)}`);
  },
  gaps(): Promise<{ count: number; gaps: { id: string; name: string; type: string }[] }> {
    return req('/api/v1/gaps');
  },
  contradictions(): Promise<{ count: number; contradictions: { id: string; name: string }[] }> {
    return req('/api/v1/contradictions');
  },
  reviewQueue(): Promise<{
    items: { id: string; label: string; name: string; review_status: string; confidence: number }[];
  }> {
    return req('/api/v1/curation/queue');
  },

  // -- Curation actions (§17.15) --------------------------------------------
  entityHistory(id: string): Promise<{ history: Record<string, unknown>[] }> {
    return req(`/api/v1/entities/${encodeURIComponent(id)}/history`);
  },
  setEntityStatus(id: string, status: string, reason = ''): Promise<Record<string, unknown>> {
    return req(`/api/v1/entities/${encodeURIComponent(id)}/status`, {
      method: 'POST',
      body: JSON.stringify({ status, reason }),
    });
  },

  // -- Entity Detail (§17.11) -----------------------------------------------
  graphNodes(label: string, limit = 40): Promise<{ count: number; nodes: NodeRow[] }> {
    return req(`/api/v1/graph/nodes?label=${encodeURIComponent(label)}&limit=${limit}`);
  },

  // -- Admin / Governance (§17.20) ------------------------------------------
  adminLineage(): Promise<{ runs: LineageRun[] }> {
    return req('/api/v1/admin/lineage');
  },
  adminTechnoeconomic(): Promise<{ solutions: string[] }> {
    return req('/api/v1/admin/technoeconomic');
  },
  adminGraphAlgos(): Promise<{ degree_centrality: { entity_id: string; score: number }[] }> {
    return req('/api/v1/admin/graph-algos');
  },
  adminCoverageMatrix(): Promise<{ matrix: { materials: string[]; properties?: string[] } }> {
    return req('/api/v1/admin/coverage-matrix');
  },
  auditTail(limit = 100): Promise<{ entries: AuditEntry[] }> {
    return req(`/api/v1/admin/audit?limit=${limit}`);
  },

  // -- Saved views (§17.16) -------------------------------------------------
  listViews(): Promise<{ views: SavedView[] }> {
    return req('/api/v1/views');
  },
  saveView(name: string, payload: Record<string, unknown>, kind = 'query'): Promise<SavedView> {
    return req('/api/v1/views', { method: 'POST', body: JSON.stringify({ name, kind, payload }) });
  },
  comparison(query: string): Promise<{
    columns: string[];
    rows: Record<string, unknown>[];
    coverage: { cells_total: number; cells_with_evidence: number; solutions: number };
  }> {
    return req('/api/v1/comparison', { method: 'POST', body: JSON.stringify({ query }) });
  },
  exportUrl: '/api/v1/export',

  // -- Chat sessions (§14.4) ------------------------------------------------
  createSession(title = ''): Promise<{ session_id: string; created_at: string; user_id: string }> {
    return req('/api/v1/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) });
  },
  listSessions(): Promise<{ sessions: ChatSession[]; count: number }> {
    return req('/api/v1/chat/sessions');
  },
  getSession(sid: string): Promise<{ session_id: string; messages: ChatMessage[] }> {
    return req(`/api/v1/chat/sessions/${encodeURIComponent(sid)}`);
  },
  postMessage(sid: string, content: string): Promise<{ message_id: string; stream_url: string }> {
    return req(`/api/v1/chat/sessions/${encodeURIComponent(sid)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  },
  chatExportUrl(sid: string, mid: string, format = 'md'): string {
    return `/api/v1/chat/sessions/${encodeURIComponent(sid)}/messages/${encodeURIComponent(mid)}/export?format=${format}`;
  },

  // -- Library / article discovery (§5) -------------------------------------
  researchSources(): Promise<{
    sources: { id: string; name: string; homepage: string; access: string; note: string }[];
  }> {
    return req('/api/v1/research/sources');
  },
  researchPlan(question: string, sourceIds?: string[]): Promise<{
    question: string;
    keywords: string[];
    sub_questions: {
      text: string;
      links: { source_id: string; source_name: string; access: string; url: string }[];
    }[];
  }> {
    return req('/api/v1/research/plan', {
      method: 'POST',
      body: JSON.stringify({ question, source_ids: sourceIds ?? null }),
    });
  },
  addArticle(body: {
    title: string;
    authors?: string[];
    year?: number | null;
    doi?: string;
    url?: string;
    source?: string;
    abstract?: string;
    domain?: string;
  }): Promise<{ paper_id: string; nodes: number; edges: number }> {
    return req('/api/v1/research/articles', { method: 'POST', body: JSON.stringify(body) });
  },
  recentArticles(): Promise<{
    articles: { id: string; title: string; year: number | null; doi: string; url: string }[];
  }> {
    return req('/api/v1/research/articles');
  },
  deepStatus(): Promise<{ available: boolean; engine: string }> {
    return req('/api/v1/research/deep/status');
  },
  deepResearch(question: string): Promise<{
    question: string;
    engine: string;
    model?: string;
    report: string;
    notes?: string[];
    plan?: unknown;
  }> {
    return req('/api/v1/research/deep', { method: 'POST', body: JSON.stringify({ question }) });
  },

  // -- Document upload → graph + viewer (§17.19) --
  async uploadDocument(file: File, useLlm = false): Promise<UploadResult> {
    const form = new FormData();
    form.append('file', file);
    // NB: do NOT set Content-Type — the browser adds the multipart boundary itself.
    const res = await fetch(`/api/v1/documents/upload?use_llm=${useLlm}`, {
      method: 'POST',
      headers: { ...authHeaders() },
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `${res.status} ${res.statusText}`);
    }
    return res.json() as Promise<UploadResult>;
  },
  listDocuments(): Promise<{ documents: DocumentMeta[]; count: number }> {
    return req('/api/v1/documents');
  },
  documentParsed(docId: string): Promise<{
    doc_id: string;
    title: string;
    page_count: number;
    pages: { page: number; text: string }[];
    tables: { page: number; rows: string[][] }[];
  }> {
    return req(`/api/v1/documents/${encodeURIComponent(docId)}/parsed`);
  },
  reindexDocument(docId: string, useLlm = false): Promise<{ status: string; node_count: number; graph: GraphResponse }> {
    return req(`/api/v1/documents/${encodeURIComponent(docId)}/reindex`, {
      method: 'POST',
      body: JSON.stringify({ use_llm: useLlm }),
    });
  },

  // -- Multimodal deep-research: analyse a figure/micrograph/screenshot (§ minimax-m3) --
  async analyzeImage(file: File, question: string): Promise<MultimodalResult> {
    const form = new FormData();
    form.append('file', file);
    form.append('question', question);
    const res = await fetch('/api/v1/research/multimodal', {
      method: 'POST',
      headers: { ...authHeaders() },
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `${res.status} ${res.statusText}`);
    }
    return res.json() as Promise<MultimodalResult>;
  },

  // -- Agentic Advisor (multi-agent recommendation) -------------------------
  advise(query: string, geography = 'all', topK = 5): Promise<AdvisorResult> {
    return req('/api/v1/advise', {
      method: 'POST',
      body: JSON.stringify({ query, geography, top_k: topK }),
    });
  },
  adviseStreamUrl(query: string, geography = 'all', topK = 5): string {
    const g = geography && geography !== 'all' ? `&geography=${encodeURIComponent(geography)}` : '';
    return `/api/v1/advise/stream?query=${encodeURIComponent(query)}&top_k=${topK}${g}`;
  },

  // -- Agentic contradiction arbiter ----------------------------------------
  contradictionsList(limit = 40): Promise<{ contradictions: ContradictionSummary[] }> {
    return req(`/api/v1/arbiter/contradictions?limit=${limit}`);
  },
  analyzeContradiction(cid: string): Promise<ContradictionAnalysis> {
    return req(`/api/v1/arbiter/${encodeURIComponent(cid)}/analyze`, { method: 'POST' });
  },

  // -- Agentic insights (командный центр + карта пробелов) ------------------
  briefing(): Promise<Briefing> {
    return req('/api/v1/insights/briefing');
  },
  gapsPrioritized(limit = 12): Promise<{ gaps: PrioritizedGap[]; count: number; usedModels: string[] }> {
    return req(`/api/v1/insights/gaps-prioritized?limit=${limit}`);
  },

  // -- §17.7 Agent reasoning trace (tool-call timeline) ---------------------
  agentReasoningTrace(
    question: string,
  ): Promise<import('./components/AgentReasoningTimelineView').ReasoningTrace> {
    return req('/api/v1/agent/reasoning-trace', {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  },

  // -- §7.5 Apples-to-apples unit normalization -----------------------------
  comparisonNormalize(
    cells: { label: string; value: number; unit: string }[],
    targetUnit?: string,
  ): Promise<NormalizeResult> {
    return req<NormalizeResult>('/api/v1/comparison/normalize', {
      method: 'POST',
      body: JSON.stringify({ cells, target_unit: targetUnit ?? null }),
    });
  },

  // -- §17.9 GraphRAG community summaries -----------------------------------
  communitySummaries(limit = 60): Promise<{ count: number; communities: CommunitySummary[] }> {
    return req(`/api/v1/graph-communities/summaries?limit=${limit}`);
  },
  communitySubgraph(communityId: number, expand = 1): Promise<GraphResponse> {
    return req(`/api/v1/graph-communities/${communityId}/subgraph?expand=${expand}`);
  },

  // -- §8.8 ER candidate review + merge -------------------------------------
  erCandidates(status = 'review_needed', type = 'Material', limit = 50): Promise<ERCandidatesResponse> {
    return req(
      `/api/v1/entities/candidates?status=${encodeURIComponent(status)}&type=${encodeURIComponent(type)}&limit=${limit}`,
    );
  },
  mergeEntities(keepId: string, dropId: string, reason = ''): Promise<Record<string, unknown>> {
    return req('/api/v1/entities/merge', {
      method: 'POST',
      body: JSON.stringify({ keep_id: keepId, drop_id: dropId, reason }),
    });
  },

  // -- §8.10 Incremental ER pipeline step -----------------------------------
  // Response shapes (ERStepStatus/ERStepPreview/ERDemoResult) are declared and
  // cast via useQuery<...> inside EntityResolutionStepView, so we keep the client
  // return loose (`any`) to satisfy those generics.
  erStepStatus(): Promise<any> {
    return req('/api/v1/ingestion/er/status');
  },
  erStepPreview(type = 'Material'): Promise<any> {
    return req(`/api/v1/ingestion/er/preview?type=${encodeURIComponent(type)}`);
  },
  erStepDemo(): Promise<any> {
    return req('/api/v1/ingestion/er/demo', { method: 'POST' });
  },

  // -- §15.9 Gap-closure experiment plan ------------------------------------
  gapClosurePlan(
    maxExperiments?: number,
    domain?: string,
    budget?: number,
  ): Promise<import('./components/GapClosurePlanView').ClosurePlanResponse> {
    const p = new URLSearchParams();
    if (maxExperiments != null) p.set('max_experiments', String(maxExperiments));
    if (domain) p.set('domain', domain);
    if (budget != null) p.set('budget', String(budget));
    const qs = p.toString();
    return req(`/api/v1/gap-closure/plan${qs ? `?${qs}` : ''}`);
  },

  // -- §17.14 Gap matrix (type × domain) ------------------------------------
  gapsMatrix(): Promise<{ matrix: Record<string, Record<string, number>> }> {
    return req('/api/v1/gaps/matrix');
  },
  gapsList(opts: { gapType?: string; domain?: string; limit?: number } = {}): Promise<{
    count: number;
    gaps: { id: string; name: string; type: string; domain: string }[];
  }> {
    const p = new URLSearchParams();
    if (opts.gapType) p.set('gap_type', opts.gapType);
    if (opts.domain) p.set('domain', opts.domain);
    if (opts.limit) p.set('limit', String(opts.limit));
    const qs = p.toString();
    return req(`/api/v1/gaps${qs ? `?${qs}` : ''}`);
  },

  // -- §7.3 Cross-scale hardness HV↔HRC↔HB (ASTM E140) ----------------------
  hardnessEquivalents(value: number, scale: string): Promise<HardnessEquivalents> {
    return req<HardnessEquivalents>('/api/v1/hardness/equivalents', {
      method: 'POST',
      body: JSON.stringify({ value, scale }),
    });
  },
  hardnessCompare(
    readings: { label: string; value: number; scale: string }[],
    targetScale = 'HV',
  ): Promise<HardnessCompareResult> {
    return req<HardnessCompareResult>('/api/v1/hardness/compare', {
      method: 'POST',
      body: JSON.stringify({ readings, target_scale: targetScale }),
    });
  },

  // -- §13.11 Link prediction (Mode D) --------------------------------------
  linkPredictionSeeds(
    label = 'Material',
  ): Promise<{ count: number; seeds: { id: string; name: string; label: string }[] }> {
    return req(`/api/v1/link-prediction/seeds?label=${encodeURIComponent(label)}`);
  },
  linkPredict(
    seed: string,
    metric = 'adamic_adar',
    targetLabel?: string,
    limit = 12,
  ): Promise<{
    seed: { id: string; name: string | null; label: string | null };
    metric: string;
    target_label: string | null;
    count: number;
    predictions: {
      target: string;
      target_name: string | null;
      target_label: string;
      metric: string;
      raw_score: number;
      score: number;
      shared_neighbors: number;
      jaccard: number;
      adamic_adar: number;
      resource_allocation: number;
      preferential: number;
      reason: string;
    }[];
  }> {
    const q = new URLSearchParams({ seed, metric, limit: String(limit) });
    if (targetLabel) q.set('target_label', targetLabel);
    return req(`/api/v1/link-prediction/predict?${q.toString()}`);
  },

  // -- §3.14 Live GDS on Neo4j (Louvain + nodeSimilarity) -------------------
  gdsStatus(): Promise<{
    available: boolean;
    profile: string;
    clustered?: boolean;
    communities?: number;
    reason?: string;
  }> {
    return req('/api/v1/gds-live/status');
  },
  gdsColoredGraph(limit = 400): Promise<GraphResponse> {
    return req(`/api/v1/gds-live/colored-graph?limit=${limit}`);
  },
  gdsCommunities(limit = 24): Promise<{
    clustered: boolean;
    count: number;
    communities: { community_id: number; size: number; top_entities: string[] }[];
  }> {
    return req(`/api/v1/gds-live/communities?limit=${limit}`);
  },
  gdsSimilar(
    seed: string,
    limit = 10,
  ): Promise<{
    seed: { id: string; name?: string; label?: string };
    count: number;
    similar: { id: string; name: string; label?: string; similarity: number }[];
  }> {
    return req(`/api/v1/gds-live/similar?seed=${encodeURIComponent(seed)}&limit=${limit}`);
  },
  gdsLouvain(): Promise<{
    run_id: string;
    community_count: number;
    modularity: number;
    nodes_written: number;
    projected: { nodes: number; relationships: number };
    communities: { community_id: number; size: number; top_entities: string[] }[];
  }> {
    return req('/api/v1/gds-live/louvain', { method: 'POST' });
  },

  // -- §8.2 Materials Project authority badge -------------------------------
  materialsProjectBadge(entityId: string): Promise<MaterialsProjectBadgeData> {
    return req(`/api/v1/entities/${encodeURIComponent(entityId)}/materials-project`);
  },

  // -- §3.14 Similarity-based implicit links --------------------------------
  simLinksSeeds(label = 'Material'): Promise<SimLinksSeeds> {
    return req(`/api/v1/similarity-links/seeds?label=${encodeURIComponent(label)}`);
  },
  simLinksSuggest(seed: string, targetLabel?: string): Promise<SimLinksSuggest> {
    const tl = targetLabel ? `&target_label=${encodeURIComponent(targetLabel)}` : '';
    return req(`/api/v1/similarity-links/suggest?seed=${encodeURIComponent(seed)}${tl}`);
  },

  // -- §6.10 Table-cell evidence tracing ------------------------------------
  evidenceTableCell(evidenceId: string): Promise<{
    isTableCell: boolean;
    source: string;
    docId: string | null;
    tableId: string | null;
    rowIndex: number | null;
    colIndex: number | null;
    grid: string[][];
    highlight: { row: number; col: number };
    cellText: string | null;
    detail: string;
    locatorValid: boolean;
  }> {
    return req(`/api/v1/evidence/${encodeURIComponent(evidenceId)}/table-cell`);
  },

  // -- §25.11 Value-of-Information ranking ----------------------------------
  // VoIResponse is declared locally in ValueOfInformationView; keep loose.
  absenceValueOfInformation(topN = 20): Promise<any> {
    return req(`/api/v1/absence/value-of-information?top_n=${topN}`);
  },

  // -- §3.14 Missing-links board (corpus feed) ------------------------------
  missingLinksBoard(
    seedLabel?: string,
    targetLabel?: string,
    limit = 25,
  ): Promise<{
    method: 'gds' | 'in_process';
    seed_label: string | null;
    target_label: string | null;
    min_similarity: number;
    count: number;
    predictions: {
      a: { id: string; name: string; label: string | null };
      b: { id: string; name: string; label: string | null };
      similarity: number;
      shared: number;
      shared_via: string[];
      reason: string;
      confidence: number;
    }[];
  }> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (seedLabel) q.set('seed_label', seedLabel);
    if (targetLabel) q.set('target_label', targetLabel);
    return req(`/api/v1/missing-links/board?${q.toString()}`);
  },
};

// -- §7.5 Apples-to-apples normalized-unit result --------------------------
export interface NormalizedCell {
  label: string;
  value_raw: number;
  unit: string;
  value_normalized: number | null;
  normalized_unit: string | null;
  normalization_method: string; // direct | converted | incompatible | unit_missing
  note: string;
}
export interface NormalizeResult {
  target_unit: string | null;
  cells: NormalizedCell[];
  all_comparable: boolean;
  min: number | null;
  max: number | null;
  spread: number | null;
  best_label: string | null;
  worst_label: string | null;
}

// -- §7.3 Cross-scale hardness result --------------------------------------
export interface HardnessScaleValue {
  scale: string;
  value: number | null;
  is_source: boolean;
}
export interface HardnessEquivalents {
  input: HardnessScaleValue;
  equivalents: HardnessScaleValue[];
  tensile_mpa: number | null;
  approximate: boolean;
  conversion_standard: string;
  normalization_method: string;
  notes: string[];
}
export interface HardnessCompareRow {
  label: string;
  original_value: number;
  original_scale: string;
  normalized_value: number | null;
  normalized_scale: string;
  hv: number | null;
  tensile_mpa: number | null;
  approximate: boolean;
  note: string;
}
export interface HardnessCompareResult {
  target_scale: string;
  rows: HardnessCompareRow[];
  hardest: string | null;
  softest: string | null;
  spread_hv: number | null;
  conversion_standard: string;
  normalization_method: string;
}

export interface MultimodalResult {
  model: string | null;
  question: string;
  filename: string;
  analysis: string;
}

export interface DocumentMeta {
  doc_id: string;
  title: string;
  doc_type: string;
  page_count: number;
  year: number | null;
  status: string;
}

export interface UploadResult {
  doc_id: string;
  title: string;
  status: string;
  page_count: number;
  chunks: number;
  graph: GraphResponse;
  node_count: number;
}
