import type {
  AnswerPayload,
  AuditEntry,
  CoverageDomain,
  GlossaryTerm,
  GraphResponse,
  LineageRun,
  NodeRow,
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
  adminCoverageMatrix(): Promise<{ matrix: { materials: string[]; properties?: string[] } }> {
    return req('/api/v1/admin/coverage-matrix');
  },
  auditTail(limit = 100): Promise<{ entries: AuditEntry[] }> {
    return req(`/api/v1/admin/audit?limit=${limit}`);
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
};

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
