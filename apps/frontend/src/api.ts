import type {
  AnswerPayload,
  CoverageDomain,
  GlossaryTerm,
  GraphResponse,
} from './types';

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface QueryOptions {
  role?: string;
  useLlm?: boolean;
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
  query(query: string, opts: QueryOptions = {}): Promise<AnswerPayload> {
    return req<AnswerPayload>('/api/v1/query', {
      method: 'POST',
      body: JSON.stringify({ query, role: opts.role ?? 'researcher', use_llm: opts.useLlm ?? true }),
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
};
