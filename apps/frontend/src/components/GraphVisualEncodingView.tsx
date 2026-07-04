import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Lock, Search, ShieldCheck, Sparkles } from 'lucide-react';
import type { GraphNode, GraphResponse } from '../types';
import { GraphView } from './GraphView';

// §3.16 / §5.2.3 — «Легенда достоверности». The «клубок» already renders the four
// visual codes (полый узел = нет данных, красное ребро = противоречие, пунктир =
// inferred, замок = verified); the backend /graph/encoding/* endpoints now FILL
// those derived fields on the live-Neo4j payload (missingFields, contradicted on
// CONTRADICTS edges, evidence counts). This screen makes the visual language
// self-explanatory: a legend card that draws each code, a live sample graph fully
// encoded, entity-neighbourhood lookup, and a selected-node panel that reads the
// trust signals off the node so «доверие читается на клубке без чтения текста».

interface EncodingSummary {
  nodes: number;
  edges: number;
  hollow: number;
  verified: number;
  contradicted: number;
  inferred: number;
}
interface EncodedGraph {
  graph: GraphResponse;
  summary: EncodingSummary;
  seed: string | null;
}
interface LegendEntry {
  key: string;
  channel: string;
  signal: string;
  label: string;
  meaning: string;
}

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

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { ...authHeaders() } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as T;
}

// A tiny SVG that draws the actual visual code, so the legend teaches the «клубок»
// language 1:1 (same copper/red/hollow conventions as GraphView's canvas).
function LegendSwatch({ kind }: { kind: string }) {
  const COPPER = '#C87941';
  const RED = '#E5484D';
  switch (kind) {
    case 'hollow':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <circle cx="8" cy="10" r="5.5" fill="none" stroke={COPPER} strokeWidth="1.6" />
          <circle cx="24" cy="10" r="5.5" fill={COPPER} />
        </svg>
      );
    case 'contradiction':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <line x1="2" y1="10" x2="32" y2="10" stroke={RED} strokeWidth="2.6" />
        </svg>
      );
    case 'inferred':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <line x1="2" y1="10" x2="32" y2="10" stroke="#C87941" strokeWidth="1.8" strokeDasharray="4 3" />
        </svg>
      );
    case 'verified':
      return (
        <span className="grid h-5 w-[34px] place-items-center">
          <Lock size={13} className="text-emerald-400" />
        </span>
      );
    case 'node_size':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <circle cx="8" cy="10" r="3" fill="#8FA3B0" />
          <circle cx="24" cy="10" r="7" fill="#8FA3B0" />
        </svg>
      );
    case 'edge_width':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <line x1="2" y1="6" x2="32" y2="6" stroke="#8FA3B0" strokeWidth="1" />
          <line x1="2" y1="14" x2="32" y2="14" stroke="#8FA3B0" strokeWidth="3.4" />
        </svg>
      );
    case 'edge_opacity':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <line x1="2" y1="10" x2="17" y2="10" stroke="#C87941" strokeWidth="2.4" opacity="0.25" />
          <line x1="17" y1="10" x2="32" y2="10" stroke="#C87941" strokeWidth="2.4" opacity="1" />
        </svg>
      );
    default:
      return <span className="inline-block h-3 w-3 rounded-full bg-faint" />;
  }
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={`font-mono text-sm font-semibold ${tone ?? 'text-nickel'}`}>{value}</span>
      <span className="font-mono text-[10px] uppercase tracking-wide text-faint">{label}</span>
    </div>
  );
}

export function GraphVisualEncodingView() {
  const [legend, setLegend] = useState<LegendEntry[]>([]);
  const [data, setData] = useState<EncodedGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<GraphNode | null>(null);

  useEffect(() => {
    getJson<{ encodings: LegendEntry[] }>('/api/v1/graph/encoding/legend')
      .then((j) => setLegend(j.encodings))
      .catch(() => setLegend([]));
  }, []);

  const loadSample = useCallback(() => {
    setLoading(true);
    setError(null);
    setSelected(null);
    getJson<EncodedGraph>('/api/v1/graph/encoding/sample?depth=2')
      .then(setData)
      .catch((e) => setError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadSample();
  }, [loadSample]);

  const loadEntity = useCallback((id: string) => {
    const trimmed = id.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    getJson<EncodedGraph>(`/api/v1/graph/encoding/neighbors/${encodeURIComponent(trimmed)}?depth=2`)
      .then(setData)
      .catch((e) => setError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  }, []);

  const summary = data?.summary;
  const graph = useMemo<GraphResponse>(() => data?.graph ?? { nodes: [], edges: [] }, [data]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-6 py-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-nickel">
          <ShieldCheck size={20} className="text-copper" /> Легенда достоверности
          <span className="font-mono text-[11px] font-normal text-faint">§5.2.3 · визуальные кодировки</span>
        </h2>
        <form
          className="ml-auto flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            loadEntity(query);
          }}
        >
          <div className="flex items-center gap-1.5 rounded border border-line bg-panel px-2">
            <Search size={13} className="text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="id сущности…"
              className="w-40 bg-transparent py-1 font-mono text-[12px] text-nickel outline-none placeholder:text-faint"
            />
          </div>
          <button
            type="button"
            onClick={loadSample}
            title="показать окрестность самого связанного узла"
            className="flex items-center gap-1 rounded bg-copper/20 px-2 py-1 font-mono text-[11px] text-copper hover:bg-copper/30"
          >
            <Sparkles size={13} /> пример
          </button>
        </form>
      </header>

      {summary && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line/60 px-6 py-2">
          <Stat label="узлов" value={summary.nodes} />
          <Stat label="рёбер" value={summary.edges} />
          <Stat label="полых · нет данных" value={summary.hollow} tone="text-copper" />
          <Stat label="противоречий" value={summary.contradicted} tone="text-[#E5484D]" />
          <Stat label="inferred" value={summary.inferred} tone="text-nickel" />
          <Stat label="проверено" value={summary.verified} tone="text-emerald-400" />
          {data?.seed && (
            <span className="ml-auto truncate font-mono text-[10px] text-faint">seed: {data.seed}</span>
          )}
        </div>
      )}

      <div className="relative flex min-h-0 flex-1">
        {/* graph canvas — reuse the shared «клубок» renderer (§5.2.3-aware) */}
        <div className="relative min-h-0 flex-1">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 font-mono text-sm text-faint">
              <Loader2 size={16} className="animate-spin text-copper" /> загрузка графа…
            </div>
          )}
          {error && !loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center font-mono text-sm text-[#E5484D]">
              {error.includes('404') ? 'сущность не найдена' : `ошибка: ${error}`}
            </div>
          )}
          {!loading && !error && graph.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center font-mono text-sm text-faint">
              граф пуст
            </div>
          )}
          <GraphView data={graph} onSelect={setSelected} selectedId={selected?.id ?? null} />

          {/* selected-node trust panel — reads the codes straight off the node */}
          {selected && (
            <div className="absolute bottom-3 right-3 z-10 w-64 rounded-lg border border-line bg-panel/95 p-3 text-sm shadow-xl backdrop-blur">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-nickel">{selected.label}</span>
                {selected.verified && <Lock size={13} className="text-emerald-400" />}
              </div>
              <dl className="mt-2 space-y-1 font-mono text-[11px] text-faint">
                <div className="flex justify-between"><dt>тип</dt><dd className="text-nickel">{selected.type}</dd></div>
                <div className="flex justify-between">
                  <dt>доказательств</dt>
                  <dd className="text-nickel">{selected.evidenceCount ?? 0}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>проверено</dt>
                  <dd className={selected.verified ? 'text-emerald-400' : 'text-nickel'}>
                    {selected.verified ? 'да (замок)' : 'нет'}
                  </dd>
                </div>
              </dl>
              {selected.missingFields && selected.missingFields.length > 0 ? (
                <div className="mt-2 rounded border border-copper/40 bg-copper/10 px-2 py-1.5">
                  <div className="font-mono text-[10px] uppercase tracking-wide text-copper">
                    нет данных · полый узел
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {selected.missingFields.map((f) => (
                      <span key={f} className="chip text-[9px] text-copper">{f}</span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-2 font-mono text-[10px] text-emerald-400/80">
                  обязательные поля заполнены
                </div>
              )}
            </div>
          )}
        </div>

        {/* legend card — teaches the visual language 1:1 */}
        <aside className="flex w-72 min-w-72 flex-col border-l border-line">
          <div className="border-b border-line px-4 py-2.5 font-mono text-[11px] uppercase tracking-wide text-faint">
            Что показывает клубок
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {legend.length === 0 && (
              <p className="px-4 py-6 text-center font-mono text-[11px] text-faint">легенда недоступна</p>
            )}
            {legend.map((e) => (
              <div key={e.key} className="border-b border-line/60 px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <LegendSwatch kind={e.key} />
                  <span className="text-[13px] font-medium text-nickel">{e.label}</span>
                </div>
                <p className="mt-1.5 text-[11px] leading-snug text-faint">{e.meaning}</p>
                <div className="mt-1 font-mono text-[9px] uppercase tracking-wide text-faint/70">
                  {e.channel} ← {e.signal}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
