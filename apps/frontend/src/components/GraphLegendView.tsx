import { useCallback, useEffect, useMemo, useState } from 'react';
import { Eye, EyeOff, Loader2, Lock, Search, Shapes, Sparkles } from 'lucide-react';
import type { GraphNode, GraphResponse } from '../types';
import { GraphView } from './GraphView';

// §17.8 — «Легенда графа»: расшифровка всех 8 визуальных кодировок §5.2.3 +
// toggle видимости каждой категории узлов/рёбер. Это делает богатую визуализацию
// «клубка» читаемой: пользователь видит, что означает каждый цвет/форма/штрих, и
// может гасить целые категории (например скрыть Evidence-узлы или CONTRADICTS-рёбра),
// чтобы разгрузить плотный подграф. Данные — живой server-профиль (Neo4j :8000)
// через новый роутер /api/v1/graph/legend/*; рендер — общий GraphView.

interface Encoding {
  key: string;
  channel: string;
  signal: string;
  label: string;
  meaning: string;
}
interface Category {
  type: string;
  count: number;
  colour?: string | null;
}
interface LegendView {
  graph: GraphResponse;
  nodeCategories: Category[];
  edgeCategories: Category[];
  summary: Record<string, number>;
  seed: string | null;
}

const DEFAULT_COLOUR = '#8FA3B0';

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

// Draws the actual §5.2.3 code so the legend teaches the «клубок» language 1:1.
function CodeSwatch({ code }: { code: Encoding }) {
  const COPPER = '#C87941';
  const RED = '#E5484D';
  switch (code.key) {
    case 'node_colour':
      return (
        <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
          <circle cx="7" cy="10" r="5" fill="#8FA3B0" />
          <circle cx="17" cy="10" r="5" fill={COPPER} />
          <circle cx="27" cy="10" r="5" fill="#6C8CD5" />
        </svg>
      );
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
          <line x1="2" y1="10" x2="32" y2="10" stroke={COPPER} strokeWidth="1.8" strokeDasharray="4 3" />
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
          <line x1="2" y1="10" x2="17" y2="10" stroke={COPPER} strokeWidth="2.4" opacity="0.25" />
          <line x1="17" y1="10" x2="32" y2="10" stroke={COPPER} strokeWidth="2.4" opacity="1" />
        </svg>
      );
    default:
      return <span className="inline-block h-3 w-3 rounded-full bg-faint" />;
  }
}

function ToggleRow({
  label,
  count,
  colour,
  visible,
  onToggle,
}: {
  label: string;
  count: number;
  colour?: string | null;
  visible: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex w-full items-center gap-2 px-4 py-1.5 text-left hover:bg-line/40 ${
        visible ? '' : 'opacity-45'
      }`}
    >
      {colour !== undefined ? (
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: colour ?? DEFAULT_COLOUR }}
        />
      ) : (
        <span className="h-0.5 w-3 shrink-0 rounded" style={{ background: '#8FA3B0' }} />
      )}
      <span className="flex-1 truncate font-mono text-[11px] text-nickel">{label}</span>
      <span className="font-mono text-[10px] text-faint">{count}</span>
      {visible ? (
        <Eye size={12} className="text-faint" />
      ) : (
        <EyeOff size={12} className="text-faint/60" />
      )}
    </button>
  );
}

export function GraphLegendView() {
  const [codes, setCodes] = useState<Encoding[]>([]);
  const [data, setData] = useState<LegendView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<GraphNode | null>(null);
  // Categories the user has HIDDEN (empty = everything visible).
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<Set<string>>(new Set());
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<Set<string>>(new Set());

  useEffect(() => {
    getJson<{ encodings: Encoding[] }>('/api/v1/graph/legend/codes')
      .then((j) => setCodes(j.encodings))
      .catch(() => setCodes([]));
  }, []);

  const load = useCallback((id?: string) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    const url = id
      ? `/api/v1/graph/legend/view?entity_id=${encodeURIComponent(id)}&depth=2`
      : '/api/v1/graph/legend/view?depth=2';
    getJson<LegendView>(url)
      .then((d) => {
        setData(d);
        // A fresh graph resets any category toggles to fully visible.
        setHiddenNodeTypes(new Set());
        setHiddenEdgeTypes(new Set());
      })
      .catch((e) => setError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleNode = useCallback((t: string) => {
    setHiddenNodeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }, []);
  const toggleEdge = useCallback((t: string) => {
    setHiddenEdgeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }, []);

  // Apply the category toggles: drop hidden-type nodes, then any edge whose type
  // is hidden or whose endpoints no longer exist. GraphView re-lays out cleanly.
  const filtered = useMemo<GraphResponse>(() => {
    const g = data?.graph ?? { nodes: [], edges: [] };
    const nodes = g.nodes.filter((n) => !hiddenNodeTypes.has(n.type));
    const kept = new Set(nodes.map((n) => n.id));
    const edges = g.edges.filter(
      (e) => !hiddenEdgeTypes.has(String(e.type)) && kept.has(e.source) && kept.has(e.target),
    );
    return { nodes, edges };
  }, [data, hiddenNodeTypes, hiddenEdgeTypes]);

  const nodeCats = data?.nodeCategories ?? [];
  const edgeCats = data?.edgeCategories ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-6 py-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-nickel">
          <Shapes size={20} className="text-copper" /> Легенда графа
          <span className="font-mono text-[11px] font-normal text-faint">
            §17.8 · 8 кодировок · toggle категорий
          </span>
        </h2>
        <form
          className="ml-auto flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (query.trim()) load(query.trim());
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
            onClick={() => load()}
            title="показать окрестность самого связанного узла"
            className="flex items-center gap-1 rounded bg-copper/20 px-2 py-1 font-mono text-[11px] text-copper hover:bg-copper/30"
          >
            <Sparkles size={13} /> пример
          </button>
        </form>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {/* left: category toggles (checkboxes to hide/show each node/edge type) */}
        <aside className="flex w-60 min-w-60 flex-col border-r border-line">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <span className="font-mono text-[11px] uppercase tracking-wide text-faint">
              Категории узлов
            </span>
            {hiddenNodeTypes.size > 0 && (
              <button
                type="button"
                onClick={() => setHiddenNodeTypes(new Set())}
                className="font-mono text-[10px] text-copper hover:underline"
              >
                показать все
              </button>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {nodeCats.length === 0 && (
              <p className="px-4 py-4 font-mono text-[10px] text-faint">нет данных</p>
            )}
            {nodeCats.map((c) => (
              <ToggleRow
                key={`n:${c.type}`}
                label={c.type}
                count={c.count}
                colour={c.colour ?? DEFAULT_COLOUR}
                visible={!hiddenNodeTypes.has(c.type)}
                onToggle={() => toggleNode(c.type)}
              />
            ))}
            <div className="flex items-center justify-between border-y border-line px-4 py-2">
              <span className="font-mono text-[11px] uppercase tracking-wide text-faint">
                Категории рёбер
              </span>
              {hiddenEdgeTypes.size > 0 && (
                <button
                  type="button"
                  onClick={() => setHiddenEdgeTypes(new Set())}
                  className="font-mono text-[10px] text-copper hover:underline"
                >
                  показать все
                </button>
              )}
            </div>
            {edgeCats.length === 0 && (
              <p className="px-4 py-4 font-mono text-[10px] text-faint">нет рёбер</p>
            )}
            {edgeCats.map((c) => (
              <ToggleRow
                key={`e:${c.type}`}
                label={c.type}
                count={c.count}
                visible={!hiddenEdgeTypes.has(c.type)}
                onToggle={() => toggleEdge(c.type)}
              />
            ))}
          </div>
        </aside>

        {/* center: the «клубок», filtered by the active category toggles */}
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
          {!loading && !error && filtered.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center font-mono text-sm text-faint">
              {(data?.graph.nodes.length ?? 0) > 0 ? 'все категории скрыты' : 'граф пуст'}
            </div>
          )}
          <GraphView data={filtered} onSelect={setSelected} selectedId={selected?.id ?? null} />
          {data?.summary && (
            <div className="pointer-events-none absolute left-3 top-3 z-10 rounded border border-line bg-panel/90 px-2.5 py-1.5 font-mono text-[10px] text-faint backdrop-blur">
              {filtered.nodes.length}/{data.graph.nodes.length} узлов ·{' '}
              {filtered.edges.length}/{data.graph.edges.length} рёбер
              {data.seed && <span className="ml-2 text-faint/70">seed: {data.seed}</span>}
            </div>
          )}
          {selected && (
            <div className="absolute bottom-3 right-3 z-10 w-60 rounded-lg border border-line bg-panel/95 p-3 text-sm shadow-xl backdrop-blur">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-nickel">{selected.label}</span>
                {selected.verified && <Lock size={13} className="text-emerald-400" />}
              </div>
              <dl className="mt-2 space-y-1 font-mono text-[11px] text-faint">
                <div className="flex justify-between">
                  <dt>тип</dt>
                  <dd className="text-nickel">{selected.type}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>доказательств</dt>
                  <dd className="text-nickel">{selected.evidenceCount ?? 0}</dd>
                </div>
              </dl>
            </div>
          )}
        </div>

        {/* right: the 8-code legend (decodes every visual channel of the «клубок») */}
        <aside className="flex w-72 min-w-72 flex-col border-l border-line">
          <div className="border-b border-line px-4 py-2.5 font-mono text-[11px] uppercase tracking-wide text-faint">
            8 кодировок графа
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {codes.length === 0 && (
              <p className="px-4 py-6 text-center font-mono text-[11px] text-faint">
                легенда недоступна
              </p>
            )}
            {codes.map((e) => (
              <div key={e.key} className="border-b border-line/60 px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <CodeSwatch code={e} />
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
