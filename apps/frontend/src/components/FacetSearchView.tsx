import { useMemo, useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { Search, Loader2, SlidersHorizontal, X, FileText, Filter } from 'lucide-react';

// §4.7 (roadmap #73) — Фасетный поисковый экран: live-агрегации + фильтр-чипы.
// Бэкенд POST /api/v1/search/faceted считает счётчики каждого фасета
// (тип / домен / источник / статус / практика / атмосфера) с учётом остальных
// выбранных фильтров (drill-down) и сужает выдачу пересечением выбранных чипов.
// Отдельный browse-режим: нет отдельного SearchView — этот экран его закрывает.

interface FacetBucket {
  value: string;
  count: number;
  selected: boolean;
}
interface FacetGroup {
  label: string;
  buckets: FacetBucket[];
}
interface FacetHit {
  id: string;
  name: string | null;
  type: string | null;
  domain: string | null;
  source_type: string | null;
  review_status: string | null;
  practice_type: string | null;
  confidence: number | null;
  doc_id: string | null;
  snippet: string | null;
}
interface FacetSearchResponse {
  query: string;
  total: number;
  count: number;
  hits: FacetHit[];
  facets: Record<string, FacetGroup>;
  active_filters: Record<string, string[]>;
  took_ms: number;
}

type Selection = Record<string, string[]>;

// Порядок фасетов в панели (ключи, отсутствующие в ответе, просто пропускаются).
const FACET_ORDER = ['type', 'domain', 'source_type', 'review_status', 'practice_type', 'atmosphere'];

function authHeaders(): Record<string, string> {
  try {
    const raw = localStorage.getItem('sb.session');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.token) return { Authorization: `Bearer ${s.token}` };
      if (s?.role) return { 'X-Role': s.role };
    }
  } catch {
    /* ignore */
  }
  return {};
}

async function fetchFacets(query: string, filters: Selection): Promise<FacetSearchResponse> {
  const res = await fetch('/api/v1/search/faceted', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ query, filters, limit: 40 }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<FacetSearchResponse>;
}

function toggle(sel: Selection, facet: string, value: string): Selection {
  const cur = sel[facet] ?? [];
  const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
  const out = { ...sel };
  if (next.length) out[facet] = next;
  else delete out[facet];
  return out;
}

function Chip({ b, onClick }: { b: FacetBucket; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={
        'flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs transition ' +
        (b.selected
          ? 'border-copper/60 bg-copper/15 text-copper'
          : 'border-line bg-surface/40 text-muted hover:border-copper/40 hover:text-nickel')
      }
    >
      <span className="min-w-0 flex-1 truncate">{b.value}</span>
      <span
        className={
          'shrink-0 rounded px-1.5 font-mono text-[10px] ' +
          (b.selected ? 'bg-copper/25 text-copper' : 'bg-surface text-faint')
        }
      >
        {b.count}
      </span>
    </button>
  );
}

export function FacetSearchView() {
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [selection, setSelection] = useState<Selection>({});

  const q = useQuery<FacetSearchResponse>({
    queryKey: ['facet-search', query, selection],
    queryFn: () => fetchFacets(query, selection),
    placeholderData: keepPreviousData,
  });

  const data = q.data;
  const hits = data?.hits ?? [];
  const activeCount = useMemo(
    () => Object.values(selection).reduce((n, v) => n + v.length, 0),
    [selection],
  );

  const facetGroups = FACET_ORDER.filter((k) => data?.facets?.[k]).map(
    (k) => [k, data!.facets[k]] as const,
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <SlidersHorizontal size={16} className="text-copper" /> Фасетный поиск
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          live-агрегации · фильтр-чипы сужают выдачу · §4.7
        </div>

        <form
          className="mt-3 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(input.trim());
          }}
        >
          <div className="relative flex-1">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="запрос или пустое поле для browse-режима…"
              className="w-full rounded-md border border-line bg-surface/60 py-2 pl-8 pr-3 text-sm text-nickel placeholder:text-faint focus:border-copper/50 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-2 text-xs text-copper transition hover:bg-copper/20"
          >
            <Search size={13} /> Найти
          </button>
        </form>

        {(activeCount > 0 || query) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 font-mono text-[10px] text-faint">
            {query && <span className="chip border-line text-faint">q: «{query}»</span>}
            {Object.entries(selection).flatMap(([facet, vals]) =>
              vals.map((v) => (
                <button
                  key={`${facet}:${v}`}
                  onClick={() => setSelection((s) => toggle(s, facet, v))}
                  className="inline-flex items-center gap-1 rounded border border-copper/40 bg-copper/10 px-1.5 py-0.5 text-copper transition hover:bg-copper/20"
                >
                  {v} <X size={10} />
                </button>
              )),
            )}
            {activeCount > 0 && (
              <button
                onClick={() => setSelection({})}
                className="ml-1 text-faint underline decoration-dotted hover:text-nickel"
              >
                сбросить всё
              </button>
            )}
          </div>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr] overflow-hidden">
        {/* Панель фасетов */}
        <aside className="min-h-0 overflow-y-auto border-r border-line p-3">
          <div className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
            <Filter size={11} /> Фасеты
          </div>
          {q.isLoading && !data ? (
            <div className="flex items-center gap-2 font-mono text-[10px] text-faint">
              <Loader2 size={12} className="animate-spin text-copper" /> счёт…
            </div>
          ) : facetGroups.length === 0 ? (
            <div className="font-mono text-[10px] text-faint">нет данных для фасетов</div>
          ) : (
            <div className="space-y-4">
              {facetGroups.map(([key, group]) => (
                <div key={key}>
                  <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-nickel">
                    {group.label}
                  </div>
                  <div className="space-y-1">
                    {group.buckets.map((b) => (
                      <Chip
                        key={b.value}
                        b={b}
                        onClick={() => setSelection((s) => toggle(s, key, b.value))}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* Выдача */}
        <div className="min-h-0 overflow-y-auto p-4">
          <div className="mb-3 flex items-center gap-3 font-mono text-[10px] text-faint">
            <span>
              {data?.total ?? 0} совпадений
              {data && data.total > hits.length ? ` · показаны первые ${hits.length}` : ''}
            </span>
            {data && <span className="ml-auto">{data.took_ms} мс</span>}
          </div>

          {q.isError ? (
            <div className="text-sm text-contradiction">Не удалось выполнить поиск.</div>
          ) : hits.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <Search size={30} className="mx-auto mb-2 text-faint" />
                <div className="font-mono text-xs text-faint">
                  ничего не найдено — ослабьте фильтры или измените запрос
                </div>
              </div>
            </div>
          ) : (
            <div className="grid gap-2">
              {hits.map((h) => (
                <div key={h.id} className="panel p-3">
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm text-nickel">
                      {h.name ?? h.id}
                    </span>
                    {h.type && (
                      <span className="chip shrink-0 border-line text-[9px] text-faint">
                        {h.type}
                      </span>
                    )}
                    {h.confidence != null && (
                      <span className="shrink-0 font-mono text-[10px] text-faint">
                        {Math.round(h.confidence * 100)}%
                      </span>
                    )}
                  </div>
                  {h.snippet && (
                    <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
                      {h.snippet}
                    </div>
                  )}
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-[10px] text-faint">
                    {h.domain && <span>{h.domain}</span>}
                    {h.source_type && <span>· {h.source_type}</span>}
                    {h.practice_type && <span>· {h.practice_type}</span>}
                    {h.review_status && h.review_status !== 'pending' && (
                      <span className="chip border-verified/40 text-[9px] text-verified">
                        {h.review_status}
                      </span>
                    )}
                    {h.doc_id && (
                      <span className="ml-auto inline-flex items-center gap-1">
                        <FileText size={10} /> {h.doc_id}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
