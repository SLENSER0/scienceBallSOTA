import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Loader2,
  Workflow,
  Clock,
  ChevronRight,
  ExternalLink,
  Cpu,
  Copy,
  Check,
  CircleDot,
  GitBranch,
} from 'lucide-react';
import { api } from '../api';

/**
 * §19.10 — LangGraph Studio: граф `scientific_agent` + live node-trace.
 *
 * Показывает то, ради чего существует Studio, но без внешнего сервиса — прямо во
 * фронте платформы: (1) топологию графа агента «как в Studio» (реальный
 * скомпилированный StateGraph + канонический §7.2-контур из graph_topology с
 * ROUTE-fan-out и retry-петлёй verifier→query_planner), и (2) live node-trace —
 * реальный прогон §18.3-дерева спанов, разложенный по узлам графа: активный путь
 * подсвечивается на диаграмме, узлы несут бейджи длительности.
 *
 * Backend: GET /api/v1/agent/studio/graph, POST /api/v1/agent/studio/trace
 * (routers/langgraph_studio.py).
 */

export interface StudioGraphNode {
  id: string;
  label: string;
  isStart: boolean;
  isEnd: boolean;
  isRetrievalBranch?: boolean;
  rationale?: string;
}

export interface StudioTopology {
  source: string;
  nodes: StudioGraphNode[];
  edges: { source: string; target: string; conditional?: boolean }[];
  mermaid: string;
  retrievalBranches?: string[];
  nodeCount: number;
  edgeCount: number;
  topologyIssues?: string[];
}

export interface StudioGraph {
  graphId: string;
  assistant: {
    graphId: string;
    entrypoint: string;
    checkpointer: string;
    compiledAvailable: boolean;
    runtime: string;
  };
  compiled: StudioTopology | null;
  canonical: StudioTopology;
}

export interface StudioNodeOverlay {
  node: string;
  label: string;
  executed: boolean;
  order: number | null;
  status: string;
  iconKey: 'done' | 'error' | 'running' | 'pending';
  offsetMs: number | null;
  durationMs: number | null;
  summary: string;
  spanId: string | null;
}

export interface StudioTrace {
  graphId: string;
  question: string;
  traceId: string;
  intent: { intent: string; confidence: number; matched: string[] } | null;
  totalDurationMs: number;
  spanCount: number;
  statusCounts: Record<string, number>;
  canonical: StudioTopology;
  nodeTrace: {
    overlay: StudioNodeOverlay[];
    executedPath: string[];
    executedNodes: string[];
    executedCount: number;
  };
  toolTrace: { stepIndex: number; node: string; tool: string; durationMs: number }[];
  openTrace: { provider: string; url: string; label: string; external: boolean };
}

// --------------------------------------------------------------------------- //
// Hand-laid Studio-style layout for the canonical §7.2 topology (12 nodes +    //
// START/END). Keyed by node id → box center; fan-out branches share one row.   //
// --------------------------------------------------------------------------- //
const BOX_W = 176;
const BOX_H = 42;
const BR_W = 138;
const CANVAS_W = 760;
const CX = CANVAS_W / 2;

type Pos = { x: number; y: number; w: number };

const LAYOUT: Record<string, Pos> = {
  START: { x: CX, y: 24, w: 90 },
  preprocess_question: { x: CX, y: 92, w: BOX_W },
  intent_classifier: { x: CX, y: 160, w: BOX_W },
  entity_resolver: { x: CX, y: 228, w: BOX_W },
  query_planner: { x: CX, y: 296, w: BOX_W },
  structured_retrieval: { x: 84, y: 386, w: BR_W },
  hybrid_retrieval: { x: 268, y: 386, w: BR_W },
  graphrag_search: { x: 452, y: 386, w: BR_W },
  gap_analyzer: { x: 636, y: 386, w: BR_W },
  evidence_assembler: { x: CX, y: 476, w: BOX_W },
  verifier: { x: CX, y: 544, w: BOX_W },
  answer_synthesizer: { x: CX, y: 612, w: BOX_W },
  visualization_payload: { x: CX, y: 680, w: BOX_W },
  END: { x: CX, y: 748, w: 90 },
};
const CANVAS_H = 792;

function anchorBottom(p: Pos) {
  return { x: p.x, y: p.y + BOX_H / 2 };
}
function anchorTop(p: Pos) {
  return { x: p.x, y: p.y - BOX_H / 2 };
}

/** Cubic path from source-bottom to target-top; back-edges (target above) curve right. */
function edgePath(a: Pos, b: Pos): string {
  if (b.y < a.y) {
    // retry back-edge: verifier → query_planner, bow out to the right.
    const sx = a.x + a.w / 2;
    const sy = a.y;
    const tx = b.x + b.w / 2;
    const ty = b.y;
    const bow = 96;
    return `M ${sx} ${sy} C ${sx + bow} ${sy}, ${tx + bow} ${ty}, ${tx} ${ty}`;
  }
  const s = anchorBottom(a);
  const t = anchorTop(b);
  const my = (s.y + t.y) / 2;
  return `M ${s.x} ${s.y} C ${s.x} ${my}, ${t.x} ${my}, ${t.x} ${t.y}`;
}

const STATUS_STROKE: Record<string, string> = {
  ok: 'var(--verified, #3fb950)',
  done: 'var(--verified, #3fb950)',
  error: 'var(--gap, #e5534b)',
};

/** SVG Studio diagram of the canonical graph with live-trace highlight. */
function GraphDiagram({
  topology,
  overlay,
  activePath,
  onPick,
  picked,
}: {
  topology: StudioTopology;
  overlay: Record<string, StudioNodeOverlay>;
  activePath: string[];
  onPick: (id: string) => void;
  picked: string | null;
}) {
  const activeSet = useMemo(() => new Set(activePath), [activePath]);

  const isActiveEdge = (s: string, t: string) =>
    activeSet.has(s) && activeSet.has(t) && !!overlay[s]?.executed === true;

  return (
    <div className="overflow-x-auto rounded-lg border border-nickel/20 bg-ink/[0.02] p-2">
      <svg
        viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
        width={CANVAS_W}
        height={CANVAS_H}
        className="mx-auto block max-w-full"
      >
        <defs>
          <marker
            id="lg-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" className="text-nickel/50" />
          </marker>
          <marker
            id="lg-arrow-hot"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#c77d3a" />
          </marker>
        </defs>

        {/* Edges */}
        {topology.edges.map((e, i) => {
          const a = LAYOUT[e.source];
          const b = LAYOUT[e.target];
          if (!a || !b) return null;
          const hot = isActiveEdge(e.source, e.target);
          const back = b.y < a.y;
          return (
            <path
              key={`e${i}`}
              d={edgePath(a, b)}
              fill="none"
              stroke={hot ? '#c77d3a' : 'currentColor'}
              className={hot ? '' : 'text-nickel/35'}
              strokeWidth={hot ? 2.4 : 1.3}
              strokeDasharray={back ? '5 4' : undefined}
              markerEnd={hot ? 'url(#lg-arrow-hot)' : 'url(#lg-arrow)'}
              opacity={hot ? 0.95 : 0.7}
            />
          );
        })}

        {/* Nodes */}
        {topology.nodes.map((n) => {
          const p = LAYOUT[n.id];
          if (!p) return null;
          const term = n.isStart || n.isEnd;
          const ov = overlay[n.id];
          const executed = ov?.executed;
          const isPicked = picked === n.id;
          const stroke = executed ? STATUS_STROKE[ov.status] ?? '#c77d3a' : 'var(--nickel, #8a8f98)';
          return (
            <g
              key={n.id}
              transform={`translate(${p.x - p.w / 2}, ${p.y - BOX_H / 2})`}
              onClick={() => onPick(n.id)}
              style={{ cursor: 'pointer' }}
            >
              <rect
                width={p.w}
                height={term ? 28 : BOX_H}
                y={term ? (BOX_H - 28) / 2 : 0}
                rx={term ? 14 : 8}
                fill={executed ? 'rgba(199,125,58,0.14)' : 'rgba(138,143,152,0.06)'}
                stroke={stroke}
                strokeWidth={isPicked ? 2.6 : executed ? 1.8 : 1.1}
                strokeOpacity={executed ? 0.9 : isPicked ? 0.9 : 0.45}
              />
              <text
                x={p.w / 2}
                y={BOX_H / 2 + 4}
                textAnchor="middle"
                className={`fill-ink font-medium ${term ? 'text-[11px]' : 'text-[12px]'}`}
                style={{ fontSize: term ? 11 : 12, pointerEvents: 'none' }}
              >
                {n.label.length > 20 ? n.label.slice(0, 19) + '…' : n.label}
              </text>
              {/* order + duration badge on executed nodes */}
              {executed && ov.durationMs != null && (
                <text
                  x={p.w - 6}
                  y={-3}
                  textAnchor="end"
                  className="fill-copper"
                  style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums', pointerEvents: 'none' }}
                >
                  {ov.order != null ? `#${ov.order + 1} · ` : ''}
                  {ov.durationMs} ms
                </text>
              )}
              {n.isRetrievalBranch && !executed && (
                <text
                  x={p.w / 2}
                  y={BOX_H + 11}
                  textAnchor="middle"
                  className="fill-faint"
                  style={{ fontSize: 9, pointerEvents: 'none' }}
                >
                  ROUTE
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function CopyMermaid({ mermaid }: { mermaid: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(mermaid);
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      }}
      className="chip inline-flex items-center gap-1 text-muted hover:text-nickel"
      title="Скопировать Mermaid-исходник графа"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? 'Скопировано' : 'Mermaid'}
    </button>
  );
}

const EXAMPLES = [
  'Влияние старения Al-Cu сплава при 180°C 2ч на твёрдость',
  'Какие пробелы в данных по прочности титановых сплавов?',
  'Сравнить режимы термообработки для стали 40Х',
];

export function LangGraphStudioView() {
  const graphQ = useQuery({
    queryKey: ['studio-graph'],
    queryFn: () => api.studioGraph(),
  });
  const [q, setQ] = useState('');
  const [picked, setPicked] = useState<string | null>(null);
  const [showMermaid, setShowMermaid] = useState(false);
  const trace = useMutation({ mutationFn: (question: string) => api.studioTrace(question) });

  const graph = graphQ.data;
  const traceData = trace.data;

  // The diagram always renders the canonical topology; overlay comes from a trace run.
  const topology = traceData?.canonical ?? graph?.canonical;

  const overlayMap = useMemo(() => {
    const m: Record<string, StudioNodeOverlay> = {};
    for (const o of traceData?.nodeTrace.overlay ?? []) m[o.node] = o;
    return m;
  }, [traceData]);

  const activePath = traceData?.nodeTrace.executedPath ?? [];

  useEffect(() => {
    setPicked(null);
  }, [traceData]);

  const submit = (text: string) => {
    if (text.trim()) trace.mutate(text.trim());
  };

  const pickedOverlay = picked ? overlayMap[picked] : null;
  const pickedNode = topology?.nodes.find((n) => n.id === picked) ?? null;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow text-copper">§19.10 · LangGraph Studio</div>
        <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
          Граф scientific_agent + live node-trace
        </h2>
        <p className="mt-1 text-sm text-muted">
          Топология графа агента «как в Studio»: канонический §7.2-контур с ROUTE-fan-out и
          retry-петлёй <code className="text-nickel">verifier→query_planner</code>. Задайте
          вопрос — реальный §18.3-прогон разложится по узлам графа, активный путь подсветится,
          узлы получат бейджи длительности.
        </p>

        {/* Assistant descriptor chips */}
        {graph && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="chip text-copper" title="graphs-маппинг из langgraph.json (§19.10)">
              <Workflow size={12} className="mr-1 inline" />
              {graph.assistant.graphId}
            </span>
            <span className="chip text-muted" title="Точка входа графа">
              <GitBranch size={12} className="mr-1 inline" />
              {graph.assistant.entrypoint}
            </span>
            <span className="chip text-muted">checkpointer · {graph.assistant.checkpointer}</span>
            <span
              className={`chip ${graph.assistant.compiledAvailable ? 'text-verified' : 'text-faint'}`}
              title="Скомпилированный StateGraph доступен в рантайме"
            >
              <CircleDot size={12} className="mr-1 inline" />
              {graph.assistant.compiledAvailable ? 'compiled' : 'spec-only'}
            </span>
            <span className="chip text-muted">
              {graph.canonical.nodeCount} nodes · {graph.canonical.edgeCount} edges
            </span>
            {graph.compiled?.mermaid && <CopyMermaid mermaid={graph.compiled.mermaid} />}
          </div>
        )}

        {/* Composer */}
        <div className="panel mt-4 p-1.5 shadow-panel focus-within:shadow-molten">
          <div className="flex items-end gap-2">
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submit(q);
                }
              }}
              rows={2}
              placeholder="Вопрос к научному агенту — прогнать через граф…"
              className="min-h-[52px] flex-1 resize-none bg-transparent px-3 py-2 text-[15px] leading-snug text-ink placeholder:text-faint focus:outline-none"
            />
            <button
              onClick={() => submit(q)}
              disabled={trace.isPending || !q.trim()}
              className="btn-copper mb-1 mr-1 flex items-center gap-1.5"
            >
              {trace.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              <span className="hidden sm:inline">Прогнать граф</span>
            </button>
          </div>
        </div>

        {!traceData && !trace.isPending && (
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setQ(ex);
                  submit(ex);
                }}
                className="chip text-muted transition-colors hover:text-nickel"
              >
                {ex}
              </button>
            ))}
          </div>
        )}

        {graphQ.isError && (
          <p className="mt-4 rounded-md bg-gap/10 px-3 py-2 text-sm text-gap">
            Не удалось загрузить топологию графа.
          </p>
        )}
        {trace.isError && (
          <p className="mt-4 rounded-md bg-gap/10 px-3 py-2 text-sm text-gap">
            Не удалось прогнать граф. Попробуйте другой вопрос.
          </p>
        )}

        {/* Trace summary header */}
        {traceData && (
          <div className="mt-6 flex flex-wrap items-center gap-2">
            {traceData.intent && (
              <span className="chip text-copper" title="Классифицированный интент (§13.8)">
                <Cpu size={12} className="mr-1 inline" />
                {traceData.intent.intent} · {(traceData.intent.confidence * 100).toFixed(0)}%
              </span>
            )}
            <span className="chip text-muted">
              <GitBranch size={12} className="mr-1 inline" />
              {traceData.nodeTrace.executedCount} узлов пройдено
            </span>
            <span className="chip text-muted">
              <Clock size={12} className="mr-1 inline" />
              {traceData.totalDurationMs} ms · {traceData.spanCount} спанов
            </span>
            {traceData.openTrace && (
              <a
                href={
                  traceData.openTrace.external
                    ? traceData.openTrace.url
                    : `/${traceData.openTrace.url}`
                }
                target={traceData.openTrace.external ? '_blank' : undefined}
                rel={traceData.openTrace.external ? 'noopener noreferrer' : undefined}
                className="btn-copper inline-flex items-center gap-1.5"
                title={`trace_id ${traceData.traceId}`}
              >
                <ExternalLink size={14} />
                {traceData.openTrace.label}
              </a>
            )}
          </div>
        )}

        {/* Main grid: diagram + inspector/timeline */}
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          <div>
            {graphQ.isLoading && (
              <div className="flex h-64 items-center justify-center text-faint">
                <Loader2 className="animate-spin" />
              </div>
            )}
            {topology && (
              <GraphDiagram
                topology={topology}
                overlay={overlayMap}
                activePath={activePath}
                onPick={(id) => setPicked((cur) => (cur === id ? null : id))}
                picked={picked}
              />
            )}
            {/* Mermaid source (compiled StateGraph — the real Studio diagram source) */}
            {graph?.compiled?.mermaid && (
              <div className="mt-2">
                <button
                  onClick={() => setShowMermaid((v) => !v)}
                  className="flex items-center gap-1 text-xs text-muted hover:text-nickel"
                >
                  <ChevronRight
                    size={13}
                    className={`transition-transform ${showMermaid ? 'rotate-90' : ''}`}
                  />
                  Mermaid скомпилированного StateGraph ({graph.compiled.nodeCount} nodes)
                </button>
                {showMermaid && (
                  <pre className="mt-1 max-h-72 overflow-auto rounded-md bg-ink/5 p-3 text-[11px] leading-relaxed text-nickel">
                    {graph.compiled.mermaid}
                  </pre>
                )}
              </div>
            )}
            {topology?.topologyIssues && topology.topologyIssues.length > 0 && (
              <p className="mt-2 rounded bg-gap/10 px-2 py-1 text-xs text-gap">
                Проблемы топологии: {topology.topologyIssues.join('; ')}
              </p>
            )}
          </div>

          {/* Right column: node inspector or execution timeline */}
          <div className="space-y-3">
            {pickedNode && (
              <div className="panel p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-ink">{pickedNode.label}</span>
                  <code className="rounded bg-ink/5 px-1 text-[11px] text-faint">
                    {pickedNode.id}
                  </code>
                </div>
                {pickedNode.rationale && (
                  <p className="mt-1 text-xs text-muted">{pickedNode.rationale}</p>
                )}
                {pickedOverlay?.executed ? (
                  <div className="mt-2 space-y-1 text-xs">
                    <div className="flex items-center gap-2 text-copper">
                      <Clock size={11} /> {pickedOverlay.durationMs} ms · шаг #
                      {(pickedOverlay.order ?? 0) + 1}
                    </div>
                    <p className="text-muted">{pickedOverlay.summary}</p>
                    {pickedOverlay.spanId && (
                      <code className="text-[10px] text-faint">span {pickedOverlay.spanId}</code>
                    )}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-faint">
                    {pickedOverlay
                      ? 'Узел не исполнялся в этом прогоне (не входит в активный путь).'
                      : 'Запустите прогон, чтобы увидеть трассу узла.'}
                  </p>
                )}
              </div>
            )}

            {traceData && (
              <div className="panel p-3">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-faint">
                  Активный путь
                </div>
                <ol className="space-y-1">
                  {traceData.nodeTrace.overlay
                    .filter((o) => o.executed)
                    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
                    .map((o) => (
                      <li
                        key={o.node}
                        onClick={() => setPicked(o.node)}
                        className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-nickel/10"
                      >
                        <span className="w-5 shrink-0 text-right font-mono text-faint">
                          {(o.order ?? 0) + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-ink">{o.label}</span>
                        <span
                          className={`shrink-0 tabular-nums ${
                            o.status === 'error' ? 'text-gap' : 'text-copper'
                          }`}
                        >
                          {o.durationMs} ms
                        </span>
                      </li>
                    ))}
                </ol>
                {Object.keys(traceData.statusCounts).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                    {Object.entries(traceData.statusCounts).map(([k, v]) => (
                      <span key={k} className="rounded bg-ink/5 px-1.5 py-0.5 text-nickel">
                        {k}: {v}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {!traceData && !graphQ.isLoading && (
              <div className="panel p-3 text-xs text-muted">
                Клик по узлу — назначение; прогон вопроса подсветит активный путь и повесит
                тайминги.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
