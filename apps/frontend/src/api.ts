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
  HighlightSearchResponse,
  LineageRun,
  MaterialsProjectBadgeData,
  NodeRow,
  PrioritizedGap,
  SavedView,
  SimilarMaterials,
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

export interface SourceTrust {
  doc_id: string;
  trust_score: number;
  trust_tier: string; // high | medium | low | untrusted
  freshness: string; // fresh | aging | stale | unknown
  warnings: string[];
}
export interface TrustedSource {
  title: string;
  url: string;
  year?: number | null;
  trust: SourceTrust;
  paper_id?: string;
  id?: string; // review id (when routed to review)
}
export interface PendingSource {
  id: string;
  source: { title: string; url: string; snippet?: string; year?: number | null };
  trust: SourceTrust;
  status: string;
}
export interface DeepResearchSource {
  title: string;
  url: string;
  snippet?: string;
  year?: number | null;
}
export interface GapAnalysisResult {
  question: string;
  have: { n_solutions: number; n_facts: number; n_papers: number; n_gaps: number };
  missing: string[];
  attention: string[];
  queries: string[];
  vision?: string;
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
  // Streaming query: retrieval artifacts (graph/citations/gaps) arrive first, then the
  // answer streams token-by-token. onEvent(type, data) fires per SSE frame. Returns an
  // abort fn. POST (not EventSource, which is GET-only) → manual SSE parse of the body.
  queryStream(
    query: string,
    opts: QueryOptions,
    onEvent: (type: string, data: unknown) => void,
  ): () => void {
    const ctrl = new AbortController();
    (async () => {
      const res = await fetch('/api/v1/query/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          query,
          role: opts.role ?? 'researcher',
          use_llm: opts.useLlm ?? true,
          geography: opts.geography && opts.geography !== 'all' ? opts.geography : null,
        }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        onEvent('error', { message: `${res.status} ${res.statusText}` });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split('\n\n');
        buf = frames.pop() ?? ''; // keep the trailing partial frame
        for (const frame of frames) {
          let ev = 'message';
          let data = '';
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) ev = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          if (!data) continue;
          try {
            onEvent(ev, JSON.parse(data));
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    })().catch((e) => {
      if ((e as Error)?.name !== 'AbortError') onEvent('error', { message: String(e) });
    });
    return () => ctrl.abort();
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
  // Gap-informed research — step 1: analyze the prompt (+ optional image) against the
  // corpus → what's missing / on-what-to-focus + web-search queries.
  analyzeGaps(
    question: string,
    image?: string | null,
  ): Promise<GapAnalysisResult> {
    return req('/api/v1/research/analyze', {
      method: 'POST',
      body: JSON.stringify({ question, image: image ?? null }),
    });
  },
  // step 2: web-search the focus queries → cited report + found sources.
  runResearch(
    question: string,
    queries: string[],
  ): Promise<{ question: string; report: string; sources: DeepResearchSource[] }> {
    return req('/api/v1/research/run', {
      method: 'POST',
      body: JSON.stringify({ question, queries }),
    });
  },
  // «Загрузить в граф»: run found sources through Source Trust, ingest high-trust,
  // route low-trust to review. Returns {ingested:[...], review:[...]} with per-source trust.
  promoteDeepSources(
    sources: { title: string; url: string; snippet?: string; year?: number | null }[],
  ): Promise<{ ingested: TrustedSource[]; review: TrustedSource[] }> {
    return req('/api/v1/research/deep/promote', {
      method: 'POST',
      body: JSON.stringify({ sources }),
    });
  },
  pendingSources(): Promise<{ items: PendingSource[] }> {
    return req('/api/v1/research/sources/pending');
  },
  approveSource(id: string): Promise<{ approved: string; paper_id: string }> {
    return req(`/api/v1/research/sources/${encodeURIComponent(id)}/approve`, { method: 'POST' });
  },
  rejectSource(id: string): Promise<{ rejected: string }> {
    return req(`/api/v1/research/sources/${encodeURIComponent(id)}/reject`, { method: 'POST' });
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
  // Per-document storage confirmation: real graph counts + Qdrant/OpenSearch membership.
  documentStorage(docId: string): Promise<DocStorage> {
    return req(`/api/v1/documents/${encodeURIComponent(docId)}/storage`);
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
  gapsPrioritizedStreamUrl(limit = 14): string {
    return `/api/v1/insights/gaps-prioritized/stream?limit=${limit}`;
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
    // Endpoint expects `k` (topK), not `limit` — sending `limit` was silently ignored.
    return req(`/api/v1/gds-live/similar?seed=${encodeURIComponent(seed)}&k=${limit}`);
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
  // `scanLimit` caps how many empty cells the backend classifies before ranking —
  // keep it modest so the (heavy) endpoint returns promptly. `init` lets callers pass
  // an AbortController signal (timeout / unmount).
  absenceValueOfInformation(topN = 20, scanLimit = 250, init?: RequestInit): Promise<any> {
    return req(
      `/api/v1/absence/value-of-information?top_n=${topN}&scan_limit=${scanLimit}`,
      init,
    );
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

  // == Batch-2 feature endpoints ============================================

  // -- §18.3 Agent trace viewer (node → tool → LLM span tree) ---------------
  agentTrace(question: string): Promise<import('./components/AgentTraceView').AgentTrace> {
    return req('/api/v1/agent/trace', {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  },

  // -- §13.23 Run transparency & reproducibility ----------------------------
  runTransparency(
    question: string,
    seed = '0',
  ): Promise<import('./components/RunTransparencyView').RunTransparency> {
    return req('/api/v1/agent/run-transparency', {
      method: 'POST',
      body: JSON.stringify({ question, seed }),
    });
  },

  // -- §17.8 Path search Material↔Property (подсветка пути) -----------------
  graphPathEndpoints(
    label = 'Material',
    limit = 200,
  ): Promise<{ label: string; count: number; nodes: import('./components/GraphPathSearchView').PathEndpoint[] }> {
    return req(`/api/v1/graph-path/endpoints?label=${encodeURIComponent(label)}&limit=${limit}`);
  },
  graphPathSearch(
    source: string,
    target: string,
    maxHops = 4,
    topN = 6,
    edgeTypes?: string[],
  ): Promise<import('./components/GraphPathSearchView').PathSearchResult> {
    return req('/api/v1/graph-path/search', {
      method: 'POST',
      body: JSON.stringify({
        source,
        target,
        max_hops: maxHops,
        top_n: topN,
        edge_types: edgeTypes ?? null,
      }),
    });
  },

  // -- §13.11/§8.13 Structural edge anomalies (Mode D graph hygiene) --------
  edgeAnomalies(limit = 500): Promise<import('./components/EdgeAnomaliesView').EdgeAnomalyReport> {
    return req(`/api/v1/edge-anomalies/report?limit=${limit}`);
  },

  // -- §6.11 Schema-constrained property-graph extraction -------------------
  propertyGraphSchema(): Promise<any> {
    return req('/api/v1/property-graph/schema');
  },
  propertyGraphConstrain(triplets: unknown[]): Promise<any> {
    return req('/api/v1/property-graph/constrain', {
      method: 'POST',
      body: JSON.stringify({ triplets }),
    });
  },
  propertyGraphAudit(): Promise<any> {
    return req('/api/v1/property-graph/audit');
  },

  // -- §3.13 Similar entities via node-embedding vector search --------------
  similarEmbStatus(): Promise<{ available: boolean; method: string; entities: number; labels?: string[] }> {
    return req('/api/v1/similar-embeddings/status');
  },
  similarEmbSeeds(label?: string): Promise<{
    count: number;
    labels: string[];
    seeds: { id: string; name: string; label: string }[];
  }> {
    const q = label ? `?label=${encodeURIComponent(label)}` : '';
    return req(`/api/v1/similar-embeddings/seeds${q}`);
  },
  similarEmbSimilar(seed: string, k = 10): Promise<{
    seed: { id: string; name?: string; label?: string };
    method: string;
    count: number;
    similar: { id: string; name: string; label: string; similarity: number; reason: string }[];
  }> {
    return req(`/api/v1/similar-embeddings/similar?seed=${encodeURIComponent(seed)}&k=${k}`);
  },
  similarEmbByText(q: string, k = 10): Promise<{
    query: string;
    method: string;
    count: number;
    similar: { id: string; name: string; label: string; similarity: number; reason: string }[];
  }> {
    return req(`/api/v1/similar-embeddings/by-text?q=${encodeURIComponent(q)}&k=${k}`);
  },

  // -- §13.11 Похожие материалы (node similarity, Mode D) -------------------
  similarMaterialsSeeds(): Promise<{
    count: number;
    seeds: { id: string; name: string; attributes: number }[];
  }> {
    return req('/api/v1/similar-materials/seeds');
  },
  similarMaterials(seed: string, k = 12, facets?: string): Promise<SimilarMaterials> {
    const f = facets ? `&facets=${encodeURIComponent(facets)}` : '';
    return req(`/api/v1/similar-materials/similar?seed=${encodeURIComponent(seed)}&k=${k}${f}`);
  },

  // -- §7.7 Suspect-value flags (curation queue) ----------------------------
  suspectValueQueue(
    flag?: string,
    severity?: string,
  ): Promise<import('./components/SuspectValuesView').SuspectQueueResponse> {
    const p = new URLSearchParams();
    if (flag) p.set('flag', flag);
    if (severity) p.set('severity', severity);
    const qs = p.toString();
    return req(`/api/v1/suspect-values/queue${qs ? `?${qs}` : ''}`);
  },
  suspectValueMeasurement(
    id: string,
  ): Promise<import('./components/SuspectValuesView').SuspectMeasurement> {
    return req(`/api/v1/suspect-values/measurement/${encodeURIComponent(id)}`);
  },

  // == Batch-3 feature endpoints ============================================

  // -- §6.13 Confidence-fusion в оркестраторе -------------------------------
  confidenceFuse(
    facts: {
      label: string | null;
      unit: string | null;
      rule?: { confidence: number; value: number | null };
      ml?: { confidence: number; value: number | null };
      llm?: { confidence: number; value: number | null };
    }[],
  ): Promise<ConfidenceFuseResult> {
    return req<ConfidenceFuseResult>('/api/v1/confidence-fusion/fuse', {
      method: 'POST',
      body: JSON.stringify({ facts }),
    });
  },
  confidenceFusionLive(limit = 4000): Promise<ConfidenceFusionLive> {
    return req<ConfidenceFusionLive>(`/api/v1/confidence-fusion/live?limit=${limit}`);
  },

  // -- §6.9 ExperimentExtract (LLM structured extraction) -------------------
  experimentExtractStatus(): Promise<{ llm_available: boolean; model: string; prose_chunks: number; note: string }> {
    return req('/api/v1/experiment-extract/status');
  },
  experimentExtractChunks(limit = 30): Promise<{ chunks: { chunk_id: string; doc_id: string; text: string; page: number | null }[]; error?: string }> {
    return req(`/api/v1/experiment-extract/chunks?limit=${limit}`);
  },
  experimentExtractRun(payload: { chunk_id?: string; text?: string; max_repairs?: number }): Promise<Record<string, unknown>> {
    return req('/api/v1/experiment-extract/extract', { method: 'POST', body: JSON.stringify(payload) });
  },

  // -- §8.9 Undo merge / обратимость (merged_from) --------------------------
  mergeHistory(limit = 100): Promise<Record<string, unknown>> {
    return req(`/api/v1/curation/merges?limit=${limit}`);
  },
  undoMerge(eventId: string, reason = ''): Promise<Record<string, unknown>> {
    return req(`/api/v1/curation/merges/${encodeURIComponent(eventId)}/undo`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  // -- §4.7 Search highlight (<em>-фрагменты по полю совпадения) ------------
  searchHighlight(
    q: string,
    opts?: { limit?: number; fragmentSize?: number; fragments?: number },
  ): Promise<HighlightSearchResponse> {
    const p = new URLSearchParams({ q });
    if (opts?.limit) p.set('limit', String(opts.limit));
    if (opts?.fragmentSize) p.set('fragment_size', String(opts.fragmentSize));
    if (opts?.fragments) p.set('fragments', String(opts.fragments));
    return req<HighlightSearchResponse>(`/api/v1/search/highlight?${p.toString()}`);
  },

  // == Batch-4 feature endpoints ============================================

  // -- §19.10 LangGraph Studio: граф scientific_agent + live node-trace ------
  studioGraph(): Promise<import('./components/LangGraphStudioView').StudioGraph> {
    return req('/api/v1/agent/studio/graph');
  },
  studioTrace(question: string): Promise<import('./components/LangGraphStudioView').StudioTrace> {
    return req('/api/v1/agent/studio/trace', {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  },

  // -- §15.8 Verifier gate: блокировка неподкреплённых чисел + scan_gaps -----
  verifierGate(
    question: string,
    answer: string,
    citations: unknown[] = [],
  ): Promise<import('./components/VerifierGateView').VerifyResult> {
    return req('/api/v1/verifier-gate/verify', {
      method: 'POST',
      body: JSON.stringify({ question, answer, citations }),
    });
  },
  verifierScanGaps(
    question: string,
  ): Promise<import('./components/VerifierGateView').ScanContext> {
    return req('/api/v1/verifier-gate/scan-gaps', {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
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

export interface DocIndex {
  chunks: number;
  qdrant: number | null;
  opensearch: number | null;
  indexed: boolean;
}
export interface DocStorage {
  doc_id: string;
  graph: { chunks: number; measurements: number; evidence: number; in_graph: boolean };
  qdrant: number | null;
  opensearch: number | null;
  indexed: boolean;
}
export interface UploadResult {
  doc_id: string;
  title: string;
  status: string;
  page_count: number;
  chunks: number;
  graph: GraphResponse;
  node_count: number;
  index?: DocIndex;
}

// -- §6.13 Confidence-fusion в оркестраторе --------------------------------
export interface FusedFactReview {
  action: string; // auto_accept | review | reject
  action_ru: string;
  priority: number;
  reasons: string[];
  needs_review: boolean;
}
export interface FusedFact {
  id: string | null;
  label: string | null;
  sources: string[];
  layer_confidences: Record<string, number>;
  fused_confidence: number;
  agreement_boost: boolean;
  reconciled_value: number | null;
  unit: string | null;
  chosen_layer: string | null;
  conflict: boolean;
  spread: number;
  review: FusedFactReview;
  explanation: string;
}
export interface ConfidenceFuseResult {
  total: number;
  auto_accept: number;
  review: number;
  reject: number;
  boosted: number;
  conflicts: number;
  facts: FusedFact[];
}
export interface ConfidenceFusionLiveCluster {
  property_name: string | null;
  material: string | null;
  unit: string | null;
  n_members: number;
  fusion: FusedFact;
}
export interface ConfidenceFusionLive {
  total_measurements: number;
  multi_layer_clusters: number;
  conflicts: number;
  boosted: number;
  clusters: ConfidenceFusionLiveCluster[];
}
