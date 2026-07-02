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
  exportUrl: '/api/v1/export',
};
