import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowRight,
  Loader2,
  Crosshair,
  Share2,
  ScanSearch,
  ShieldCheck,
  TriangleAlert,
  Sparkles,
  Brain,
  CheckCircle2,
  XCircle,
  Circle,
  ChevronRight,
  Clock,
  Cpu,
  ExternalLink,
  GitBranch,
  Hash,
} from 'lucide-react';
import { api } from '../api';

/**
 * §18.3 — Agent trace viewer: дерево спанов node→tool→LLM + кнопка «open trace».
 *
 * Усиливает готовую agent-transparency (§17.7 «Ход мысли») до полноценного
 * ДЕРЕВА трассировки: корневой trace → графовые узлы (§7.5) → tool-спаны
 * (реальные Cypher-чтения по живому графу) → LLM-спан синтеза. Каждый спан несёт
 * настоящие span_id/trace_id (§18.2), тайминги, статус и доменные атрибуты
 * (kg.* / tool.* / llm.*). Кнопка «open trace» ведёт в LangSmith / OTel, если они
 * сконфигурированы, иначе — на внутренний permalink этого вьювера.
 *
 * Backend: POST /api/v1/agent/trace (routers/agent_trace.py).
 */

export interface TraceSpan {
  spanId: string;
  parentSpanId: string | null;
  traceId: string;
  kind: 'node' | 'tool' | 'llm';
  node: string;
  name: string;
  label: string;
  status: string;
  iconKey: 'done' | 'error' | 'running' | 'pending';
  offsetMs: number;
  durationMs: number;
  summary: string;
  rationale?: string;
  error?: string | null;
  attributes: Record<string, unknown>;
  detail?: Record<string, unknown>;
  children: TraceSpan[];
}

export interface OpenTrace {
  provider: 'langsmith' | 'otel' | 'internal';
  url: string;
  label: string;
  external: boolean;
}

export interface AgentTrace {
  question: string;
  traceId: string;
  rootSpanId: string;
  traceparent: string;
  intent: { intent: string; confidence: number; matched: string[] } | null;
  tokens: string[];
  totalDurationMs: number;
  spanCount: number;
  nodeCount: number;
  toolCount: number;
  llmCount: number;
  statusCounts: Record<string, number>;
  tree: TraceSpan[];
  toolTrace: {
    stepIndex: number;
    node: string;
    tool: string;
    kind: string;
    spanId: string;
    status: string;
    durationMs: number;
    summary: string;
  }[];
  tracingConfig: {
    agentTracing: string;
    langsmithConfigured: boolean;
    otelConfigured: boolean;
    project: string;
  };
  openTrace: OpenTrace;
}

const NODE_ICON: Record<string, typeof Crosshair> = {
  intent_classifier: Cpu,
  entity_resolver: Crosshair,
  query_planner: Share2,
  hybrid_retrieval: ScanSearch,
  evidence_verifier: ShieldCheck,
  gap_analyzer: TriangleAlert,
  answer_synthesizer: Sparkles,
};

function StatusMark({ iconKey }: { iconKey: TraceSpan['iconKey'] }) {
  if (iconKey === 'done') return <CheckCircle2 size={15} className="text-verified" />;
  if (iconKey === 'error') return <XCircle size={15} className="text-gap" />;
  if (iconKey === 'running') return <Loader2 size={15} className="animate-spin text-copper" />;
  return <Circle size={15} className="text-faint" />;
}

const EXAMPLES = [
  'Влияние старения Al-Cu сплава при 180°C 2ч на твёрдость',
  'Какие пробелы в данных по прочности титановых сплавов?',
  'Сравнить режимы термообработки для стали 40Х',
];

/** One leaf span (tool or LLM) rendered under its graph node. */
function LeafSpan({ span }: { span: TraceSpan }) {
  const [open, setOpen] = useState(false);
  const isLlm = span.kind === 'llm';
  const attrs = Object.entries(span.attributes);
  return (
    <div className="relative pl-8">
      <div className="absolute left-2 top-2 h-3 w-3 rounded-full bg-graphite ring-2 ring-nickel/30" />
      <button
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-left transition-colors hover:bg-nickel/10"
      >
        {isLlm ? (
          <Brain size={14} className="shrink-0 text-copper" strokeWidth={1.75} />
        ) : (
          <GitBranch size={14} className="shrink-0 text-nickel" strokeWidth={1.75} />
        )}
        <span
          className={`shrink-0 rounded px-1.5 text-[10px] font-medium uppercase tracking-wide ${
            isLlm ? 'bg-copper/15 text-copper' : 'bg-nickel/15 text-nickel'
          }`}
        >
          {span.kind}
        </span>
        <code className="min-w-0 flex-1 truncate text-xs text-muted">{span.name}</code>
        <StatusMark iconKey={span.iconKey} />
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-faint">
          <Clock size={10} />
          {span.durationMs} ms
        </span>
        <ChevronRight
          size={13}
          className={`shrink-0 text-faint transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>

      {open && (
        <div className="mb-1 ml-2 space-y-2 rounded-md border-l border-nickel/40 bg-ink/[0.03] px-3 py-2 text-xs">
          <p className="text-muted">{span.summary}</p>
          {span.error && (
            <p className="rounded bg-gap/10 px-2 py-1 text-gap">error: {span.error}</p>
          )}
          {/* span attributes (kg.* / tool.* / llm.*) */}
          {attrs.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {attrs.map(([k, v]) => (
                <span
                  key={k}
                  className="rounded bg-ink/5 px-1.5 py-0.5 font-mono text-[10px] text-nickel"
                  title={`${k}`}
                >
                  <span className="text-faint">{k}</span>={String(v)}
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 text-[10px] text-faint">
            <span className="inline-flex items-center gap-1">
              <Hash size={9} />
              span {span.spanId}
            </span>
            {span.parentSpanId && <span>← parent {span.parentSpanId}</span>}
          </div>
          {span.detail && Object.keys(span.detail).length > 0 && (
            <pre className="max-h-52 overflow-auto rounded bg-ink/5 p-2 text-[11px] text-nickel">
              {JSON.stringify(span.detail, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/** One graph node span (parent) with its child tool/LLM span. */
function NodeSpan({ span }: { span: TraceSpan }) {
  const [open, setOpen] = useState(true);
  const Icon = NODE_ICON[span.node] ?? Cpu;
  const attrs = Object.entries(span.attributes).filter(([k]) => k !== 'kg.node');
  return (
    <div className="relative pl-10">
      <div className="absolute left-2.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-nickel/15 ring-2 ring-graphite">
        <StatusMark iconKey={span.iconKey} />
      </div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-nickel/10"
      >
        <Icon size={16} className="shrink-0 text-copper" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-ink">{span.label}</span>
            <code className="hidden shrink-0 rounded bg-ink/5 px-1 text-[11px] text-faint sm:inline">
              {span.node}
            </code>
          </div>
          <div className="truncate text-xs text-muted">{span.summary}</div>
        </div>
        {attrs.map(([k, v]) => (
          <span
            key={k}
            className="hidden shrink-0 rounded bg-copper/10 px-1.5 py-0.5 font-mono text-[10px] text-copper lg:inline"
          >
            {k.replace('kg.', '')}={String(v)}
          </span>
        ))}
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-faint">
          <Clock size={11} />
          {span.durationMs} ms
        </span>
        <ChevronRight
          size={14}
          className={`shrink-0 text-faint transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>

      {open && (
        <div className="ml-3 mb-1 border-l border-nickel/30 pb-1">
          {span.rationale && (
            <p className="px-3 py-1 text-[11px] italic text-faint">{span.rationale}</p>
          )}
          {span.children.map((c) => (
            <LeafSpan key={c.spanId} span={c} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Standalone «open trace» button — usable both here and in the chat panel
 * (§17.7 Agent transparency). Given an {@link OpenTrace} descriptor it renders the
 * provider-aware link: opens LangSmith / OTel in a new tab, or navigates to the
 * internal trace permalink.
 */
export function OpenTraceButton({ openTrace, traceId }: { openTrace: OpenTrace; traceId: string }) {
  const providerLabel =
    openTrace.provider === 'langsmith'
      ? 'LangSmith'
      : openTrace.provider === 'otel'
        ? 'OTel'
        : 'internal';
  return (
    <a
      href={openTrace.external ? openTrace.url : `/${openTrace.url}`}
      target={openTrace.external ? '_blank' : undefined}
      rel={openTrace.external ? 'noopener noreferrer' : undefined}
      className="btn-copper inline-flex items-center gap-1.5"
      title={`trace_id ${traceId} · ${providerLabel}`}
    >
      <ExternalLink size={14} />
      {openTrace.label}
      <span className="rounded bg-white/20 px-1 text-[10px]">{providerLabel}</span>
    </a>
  );
}

export function AgentTraceView() {
  const [q, setQ] = useState('');
  const trace = useMutation({
    mutationFn: (question: string) => api.agentTrace(question),
  });
  const data = trace.data;

  const submit = (text: string) => {
    if (text.trim()) trace.mutate(text.trim());
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow text-copper">§18.3 · Agent trace viewer</div>
        <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
          Дерево трассировки агента
        </h2>
        <p className="mt-1 text-sm text-muted">
          Полное дерево спанов <b>node → tool → LLM</b> одного chat-запроса: графовые узлы
          (§7.5), под ними реальные tool-вызовы по живому графу и LLM-спан синтеза. Тайминги,
          статусы, span_id/trace_id и доменные атрибуты (kg.* / tool.* / llm.*).
        </p>

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
              placeholder="Вопрос к научному агенту…"
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
              <span className="hidden sm:inline">Построить трейс</span>
            </button>
          </div>
        </div>

        {/* Example prompts */}
        {!data && !trace.isPending && (
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

        {trace.isError && (
          <p className="mt-4 rounded-md bg-gap/10 px-3 py-2 text-sm text-gap">
            Не удалось построить трейс. Попробуйте другой вопрос.
          </p>
        )}

        {/* Result */}
        {data && (
          <div className="mt-6">
            {/* Header: intent + totals + open trace */}
            <div className="flex flex-wrap items-center gap-2">
              {data.intent && (
                <span className="chip text-copper" title="Классифицированный интент (§13.8)">
                  <Cpu size={12} className="mr-1 inline" />
                  {data.intent.intent} · {(data.intent.confidence * 100).toFixed(0)}%
                </span>
              )}
              <span className="chip text-muted">
                <GitBranch size={12} className="mr-1 inline" />
                {data.nodeCount} node · {data.toolCount} tool · {data.llmCount} llm
              </span>
              <span className="chip text-muted">
                <Clock size={12} className="mr-1 inline" />
                {data.totalDurationMs} ms · {data.spanCount} спанов
              </span>
              <span className="chip text-verified">{data.statusCounts.ok ?? 0} ok</span>
              {(data.statusCounts.error ?? 0) > 0 && (
                <span className="chip text-gap">{data.statusCounts.error} error</span>
              )}
              <div className="ml-auto">
                <OpenTraceButton openTrace={data.openTrace} traceId={data.traceId} />
              </div>
            </div>

            {/* trace id line */}
            <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[11px] text-faint">
              <span className="inline-flex items-center gap-1">
                <Hash size={10} />
                trace_id {data.traceId}
              </span>
              <span>root {data.rootSpanId}</span>
              <span className="rounded bg-ink/5 px-1.5 py-0.5">
                tracing: {data.tracingConfig.agentTracing}
                {data.tracingConfig.langsmithConfigured && ' · langsmith'}
                {data.tracingConfig.otelConfigured && ' · otel'}
              </span>
            </div>

            {data.openTrace.provider === 'internal' && (
              <p className="mt-2 text-[11px] text-faint">
                LangSmith / OTel не сконфигурированы — «open trace» ведёт на внутренний
                permalink этого трейса. Задайте <code>LANGSMITH_API_KEY</code> +{' '}
                <code>LANGCHAIN_PROJECT</code> или <code>OTEL_EXPORTER_OTLP_ENDPOINT</code>,
                чтобы линковать в внешний трейс-бэкенд.
              </p>
            )}

            {/* Span tree */}
            <div className="relative mt-5">
              <div className="absolute left-[19px] top-2 bottom-2 w-px bg-nickel/25" />
              <div className="space-y-1">
                {data.tree.map((n) => (
                  <NodeSpan key={n.spanId} span={n} />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
