import { useMemo, useRef, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Database,
  GitBranch,
  Layers,
  Loader2,
  Minus,
  Play,
  Plus,
  Workflow,
  XCircle,
  Ban,
} from 'lucide-react';

// §17.15 — Единый pipeline/agent DAG (ingestion §9.1 + LangGraph агент §7.2) со
// статусами. Backbone-визуализация «source→parse→…→index + LangGraph nodes».
//
// React Flow (@xyflow/react) не подключён в этот bundle, поэтому DAG рендерится
// self-contained SVG-канвасом в той же парадигме, что и React Flow: узлы с
// абсолютными координатами (dagre-подобная ярусная раскладка приходит с бэка),
// типизированные рёбра (pipeline / route / retry / bridge) и live-статусы.
// Компонент самодостаточен (без правок api.ts): ходит на роутер напрямую с той
// же session-auth конвенцией, что и api.ts.

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

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------- types ----
interface DagNode {
  id: string;
  section: 'ingest' | 'agent';
  kind: string;
  label: string;
  ref: string;
  status: string;
  layer: number;
  position: { x: number; y: number };
  isStore?: boolean;
  isRetrievalBranch?: boolean;
  rationale?: string;
  metricKey?: string;
  metricValue?: number;
}
interface DagEdge {
  id: string;
  source: string;
  target: string;
  kind: 'pipeline' | 'route' | 'retry' | 'bridge';
}
interface Lane {
  id: string;
  label: string;
  y: number;
}
interface LatestRun {
  job_id: string;
  status: string;
  n_documents: number;
  n_chunks: number;
  n_triples: number;
  created_at: string;
}
interface TraceSummary {
  traceId?: string | null;
  intent?: string | null;
  totalDurationMs?: number | null;
  spanCount?: number | null;
  executedNodes?: string[];
  executedCount?: number;
}
interface DagResponse {
  graphId: string;
  lanes: Lane[];
  nodes: DagNode[];
  edges: DagEdge[];
  counts: {
    nodes: number;
    edges: number;
    ingestNodes: number;
    agentNodes: number;
    bridges: number;
  };
  latestRun: LatestRun | null;
  question?: string;
  trace?: TraceSummary;
}

// --------------------------------------------------------------- layout ----
const NODE_W = 176;
const NODE_H = 58;
const PAD = 60;

const METRIC_LABEL: Record<string, string> = {
  n_documents: 'док.',
  n_chunks: 'чанков',
  n_triples: 'триплетов',
};

// status → цвет обводки/заливки/текста (RGBA поверх panel).
const STATUS_STYLE: Record<string, { stroke: string; fill: string; text: string }> = {
  success: { stroke: '#34d399', fill: 'rgba(52,211,153,0.10)', text: '#34d399' },
  ok: { stroke: '#34d399', fill: 'rgba(52,211,153,0.10)', text: '#34d399' },
  failed: { stroke: '#f87171', fill: 'rgba(248,113,113,0.12)', text: '#f87171' },
  error: { stroke: '#f87171', fill: 'rgba(248,113,113,0.12)', text: '#f87171' },
  blocked: { stroke: '#fbbf24', fill: 'rgba(251,191,36,0.10)', text: '#fbbf24' },
  running: { stroke: '#38bdf8', fill: 'rgba(56,189,248,0.10)', text: '#38bdf8' },
  skipped: { stroke: 'rgba(255,255,255,0.14)', fill: 'rgba(255,255,255,0.02)', text: '#5A6270' },
  idle: { stroke: 'rgba(255,255,255,0.14)', fill: 'rgba(255,255,255,0.03)', text: '#5A6270' },
  'n/a': { stroke: 'rgba(255,255,255,0.14)', fill: 'rgba(255,255,255,0.03)', text: '#5A6270' },
};

const EDGE_STYLE: Record<string, { stroke: string; dash?: string; label: string }> = {
  pipeline: { stroke: 'rgba(233,230,223,0.28)', label: 'pipeline' },
  route: { stroke: '#C87941', dash: '5 4', label: 'ROUTE fan-out' },
  retry: { stroke: '#fbbf24', dash: '2 4', label: 'retry-петля' },
  bridge: { stroke: '#a78bfa', dash: '6 4', label: 'мост ingest→agent' },
};

function statusStyle(s: string) {
  return STATUS_STYLE[s] ?? STATUS_STYLE.idle;
}

function StatusDot({ status }: { status: string }) {
  const st = statusStyle(status);
  if (status === 'success' || status === 'ok')
    return <CheckCircle2 size={13} style={{ color: st.text }} />;
  if (status === 'failed' || status === 'error')
    return <XCircle size={13} style={{ color: st.text }} />;
  if (status === 'blocked') return <AlertTriangle size={13} style={{ color: st.text }} />;
  if (status === 'running')
    return <Loader2 size={13} className="animate-spin" style={{ color: st.text }} />;
  if (status === 'skipped') return <Ban size={13} style={{ color: st.text }} />;
  return <CircleDashed size={13} style={{ color: st.text }} />;
}

// Ортогональное ребро source→target (правый край источника → левый край цели),
// или для мостов/ретраев — плавная кривая. Возвращает SVG path d.
function edgePath(a: DagNode, b: DagNode, kind: string): string {
  const x1 = a.position.x + NODE_W;
  const y1 = a.position.y + NODE_H / 2;
  const x2 = b.position.x;
  const y2 = b.position.y + NODE_H / 2;
  if (kind === 'bridge' || kind === 'retry' || y1 !== y2 || x2 < x1) {
    const c1x = x1 + Math.max(40, (x2 - x1) / 2);
    const c2x = x2 - Math.max(40, (x2 - x1) / 2);
    return `M ${x1} ${y1} C ${c1x} ${y1}, ${c2x} ${y2}, ${x2} ${y2}`;
  }
  const midx = (x1 + x2) / 2;
  return `M ${x1} ${y1} L ${midx} ${y1} L ${midx} ${y2} L ${x2} ${y2}`;
}

function fmt(n: number): string {
  return n.toLocaleString('ru-RU');
}

// ---------------------------------------------------------------- view -----
export function PipelineAgentDagView() {
  const [question, setQuestion] = useState('');
  const [overlay, setOverlay] = useState<DagResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [zoom, setZoom] = useState(0.85);
  const scrollRef = useRef<HTMLDivElement>(null);

  const base = useQuery({
    queryKey: ['pipeline-dag-graph'],
    queryFn: () => apiGet<DagResponse>('/api/v1/pipeline-dag/graph'),
  });

  const trace = useMutation({
    mutationFn: (q: string) => apiPost<DagResponse>('/api/v1/pipeline-dag/trace', { question: q }),
    onSuccess: (data) => setOverlay(data),
  });

  // Активный источник графа: наложенная трасса, если есть, иначе базовый.
  const dag = overlay ?? base.data ?? null;

  const bounds = useMemo(() => {
    if (!dag) return { w: 800, h: 400 };
    let maxX = 0;
    let maxY = 0;
    for (const n of dag.nodes) {
      maxX = Math.max(maxX, n.position.x + NODE_W);
      maxY = Math.max(maxY, n.position.y + NODE_H);
    }
    return { w: maxX + PAD, h: maxY + PAD };
  }, [dag]);

  const nodeById = useMemo(() => {
    const m = new Map<string, DagNode>();
    if (dag) for (const n of dag.nodes) m.set(n.id, n);
    return m;
  }, [dag]);

  const selectedNode = selected ? nodeById.get(selected) : undefined;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-white/10 px-6 py-4">
        <div className="eyebrow mb-1">backbone · §17.15</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Pipeline / Agent DAG</h2>
        <p className="max-w-4xl text-sm text-faint">
          Единый DAG всего бэкбона: ingestion-конвейер §9.1 (source → parse → chunk → extract →
          resolve → index) и узлы LangGraph-агента §7.2 (<span className="font-mono">scientific_agent</span>),
          связанные мостом — агент читает те же обслуживающие хранилища (Neo4j · Qdrant · OpenSearch),
          что строит конвейер. Живые статусы шагов — из последнего трассируемого прогона (§10.5); прогон
          агента накладывается по вопросу (§18.3-трасса).
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 border-b border-white/10 px-6 py-3">
        <div className="flex items-center gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && question.trim()) trace.mutate(question.trim());
            }}
            placeholder="Вопрос для live-прогона агента…"
            className="w-72 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-ink outline-none focus:border-copper/50"
          />
          <button
            onClick={() => question.trim() && trace.mutate(question.trim())}
            disabled={!question.trim() || trace.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-copper/40 bg-copper/10 px-3 py-1.5 text-sm text-copper hover:bg-copper/20 disabled:opacity-40"
          >
            {trace.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Прогнать агента
          </button>
          {overlay && (
            <button
              onClick={() => {
                setOverlay(null);
                setSelected(null);
              }}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-sm text-faint hover:text-ink"
            >
              Сбросить трассу
            </button>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setZoom((z) => Math.max(0.4, z - 0.1))}
            className="rounded-md border border-white/10 p-1.5 text-faint hover:text-ink"
            aria-label="zoom out"
          >
            <Minus size={14} />
          </button>
          <span className="w-10 text-center font-mono text-xs text-faint">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom((z) => Math.min(1.8, z + 0.1))}
            className="rounded-md border border-white/10 p-1.5 text-faint hover:text-ink"
            aria-label="zoom in"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>

      {/* Legend + rollup */}
      {dag && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-white/10 px-6 py-2 text-xs text-faint">
          <span className="inline-flex items-center gap-1">
            <Layers size={12} /> Ingest §9.1: {dag.counts.ingestNodes}
          </span>
          <span className="inline-flex items-center gap-1">
            <Workflow size={12} /> Agent §7.2: {dag.counts.agentNodes}
          </span>
          <span className="inline-flex items-center gap-1">
            <GitBranch size={12} /> Мостов: {dag.counts.bridges}
          </span>
          {Object.entries(EDGE_STYLE).map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              <svg width="22" height="8">
                <line
                  x1="0"
                  y1="4"
                  x2="22"
                  y2="4"
                  stroke={v.stroke}
                  strokeWidth="2"
                  strokeDasharray={v.dash}
                />
              </svg>
              {v.label}
            </span>
          ))}
          {dag.latestRun && (
            <span className="ml-auto inline-flex items-center gap-2">
              <Activity size={12} /> Последний прогон:
              <span style={{ color: statusStyle(dag.latestRun.status.toLowerCase()).text }}>
                {dag.latestRun.status}
              </span>
              · {fmt(dag.latestRun.n_documents)} док · {fmt(dag.latestRun.n_chunks)} чанков ·{' '}
              {fmt(dag.latestRun.n_triples)} триплетов
            </span>
          )}
        </div>
      )}

      {/* Canvas + detail */}
      <div className="flex min-h-0 flex-1">
        <div ref={scrollRef} className="relative flex-1 overflow-auto bg-black/20 p-4">
          {base.isLoading && (
            <div className="flex items-center gap-2 p-6 text-sm text-faint">
              <Loader2 size={16} className="animate-spin" /> Загрузка DAG…
            </div>
          )}
          {base.isError && (
            <div className="panel m-4 border-red-500/40 p-3 text-sm text-red-400">
              Ошибка: {(base.error as Error).message}
            </div>
          )}
          {trace.isError && (
            <div className="panel m-4 border-red-500/40 p-3 text-sm text-red-400">
              Ошибка трассы: {(trace.error as Error).message}
            </div>
          )}
          {dag && (
            <svg
              width={bounds.w * zoom}
              height={bounds.h * zoom}
              viewBox={`0 0 ${bounds.w} ${bounds.h}`}
              className="block"
            >
              <defs>
                {Object.entries(EDGE_STYLE).map(([k, v]) => (
                  <marker
                    key={k}
                    id={`arrow-${k}`}
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="7"
                    markerHeight="7"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={v.stroke} />
                  </marker>
                ))}
              </defs>

              {/* Lane labels */}
              {dag.lanes.map((lane) => (
                <text
                  key={lane.id}
                  x={4}
                  y={lane.y - 14}
                  fill="#5A6270"
                  fontSize="12"
                  fontFamily="monospace"
                >
                  {lane.label}
                </text>
              ))}

              {/* Edges */}
              {dag.edges.map((e) => {
                const a = nodeById.get(e.source);
                const b = nodeById.get(e.target);
                if (!a || !b) return null;
                const style = EDGE_STYLE[e.kind] ?? EDGE_STYLE.pipeline;
                const dim = selected && e.source !== selected && e.target !== selected;
                return (
                  <path
                    key={e.id}
                    d={edgePath(a, b, e.kind)}
                    fill="none"
                    stroke={style.stroke}
                    strokeWidth={e.kind === 'pipeline' ? 1.5 : 2}
                    strokeDasharray={style.dash}
                    markerEnd={`url(#arrow-${e.kind})`}
                    opacity={dim ? 0.15 : 0.9}
                  />
                );
              })}

              {/* Nodes */}
              {dag.nodes.map((n) => {
                const st = statusStyle(n.status);
                const isSel = n.id === selected;
                const Icon = n.isStore ? Database : n.section === 'agent' ? Workflow : Layers;
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.position.x}, ${n.position.y})`}
                    onClick={() => setSelected(isSel ? null : n.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={10}
                      fill={st.fill}
                      stroke={st.stroke}
                      strokeWidth={isSel ? 2.5 : 1.5}
                    />
                    <rect width={4} height={NODE_H} rx={2} fill={st.stroke} />
                    <foreignObject x={10} y={6} width={NODE_W - 18} height={NODE_H - 10}>
                      <div className="flex h-full flex-col justify-center">
                        <div className="flex items-center gap-1.5">
                          <Icon size={13} style={{ color: st.text, flexShrink: 0 }} />
                          <span className="truncate text-[12px] font-medium text-ink">
                            {n.label}
                          </span>
                        </div>
                        <div className="mt-0.5 flex items-center gap-1 text-[10px]">
                          <StatusDot status={n.status} />
                          <span style={{ color: st.text }}>{n.status}</span>
                          {n.metricKey && n.metricValue != null && (
                            <span className="ml-auto font-mono text-faint">
                              {fmt(n.metricValue)} {METRIC_LABEL[n.metricKey] ?? ''}
                            </span>
                          )}
                        </div>
                      </div>
                    </foreignObject>
                  </g>
                );
              })}
            </svg>
          )}
        </div>

        {/* Detail sidebar */}
        {(selectedNode || (overlay && overlay.trace)) && (
          <div className="w-80 shrink-0 overflow-y-auto border-l border-white/10 p-4">
            {selectedNode && (
              <div className="mb-4">
                <div className="eyebrow mb-1">{selectedNode.section} · §17.15</div>
                <h3 className="mb-1 font-display text-lg">{selectedNode.label}</h3>
                <div className="mb-2 font-mono text-xs text-faint">{selectedNode.ref}</div>
                <div className="mb-3 inline-flex items-center gap-1.5">
                  <StatusDot status={selectedNode.status} />
                  <span
                    className="text-sm"
                    style={{ color: statusStyle(selectedNode.status).text }}
                  >
                    {selectedNode.status}
                  </span>
                </div>
                <div className="space-y-1.5 text-xs text-faint">
                  <div>
                    Дорожка: <span className="text-ink">{selectedNode.section}</span>
                  </div>
                  <div>
                    Тип: <span className="text-ink">{selectedNode.kind}</span>
                  </div>
                  <div>
                    Ярус: <span className="text-ink">{selectedNode.layer}</span>
                  </div>
                  {selectedNode.isRetrievalBranch && (
                    <div className="text-copper">ROUTE-ветка извлечения (§7.2)</div>
                  )}
                  {selectedNode.metricKey && selectedNode.metricValue != null && (
                    <div>
                      {METRIC_LABEL[selectedNode.metricKey] ?? selectedNode.metricKey}:{' '}
                      <span className="text-ink">{fmt(selectedNode.metricValue)}</span>
                    </div>
                  )}
                  {selectedNode.rationale && (
                    <p className="mt-2 leading-relaxed text-faint">{selectedNode.rationale}</p>
                  )}
                </div>
              </div>
            )}

            {overlay?.trace && (
              <div className="panel p-3">
                <div className="mb-2 text-xs uppercase tracking-wide text-faint">Live-трасса агента</div>
                <div className="space-y-1 text-xs text-faint">
                  {overlay.question && (
                    <div className="mb-1 text-ink">«{overlay.question}»</div>
                  )}
                  {overlay.trace.intent && (
                    <div>
                      Интент: <span className="text-copper">{overlay.trace.intent}</span>
                    </div>
                  )}
                  {overlay.trace.totalDurationMs != null && (
                    <div>
                      Длительность:{' '}
                      <span className="text-ink">
                        {Math.round(overlay.trace.totalDurationMs)} мс
                      </span>
                    </div>
                  )}
                  {overlay.trace.spanCount != null && (
                    <div>
                      Спанов: <span className="text-ink">{overlay.trace.spanCount}</span>
                    </div>
                  )}
                  <div>
                    Исполнено узлов:{' '}
                    <span className="text-ink">{overlay.trace.executedCount ?? 0}</span>
                  </div>
                  {overlay.trace.executedNodes && overlay.trace.executedNodes.length > 0 && (
                    <div className="mt-1 font-mono text-[11px] text-faint">
                      {overlay.trace.executedNodes.join(' → ')}
                    </div>
                  )}
                  {overlay.trace.traceId && (
                    <div className="mt-1 truncate font-mono text-[10px] text-faint">
                      trace: {overlay.trace.traceId}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
