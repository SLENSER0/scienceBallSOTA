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
  CheckCircle2,
  XCircle,
  Circle,
  ChevronRight,
  Clock,
  Cpu,
} from 'lucide-react';
import { api } from '../api';

/**
 * §17.7 — Tool-call timeline агента: «как агент думает по шагам»
 * (resolve → graph → vector → evidence → gap). Прогоняет живой reasoning-trace
 * по графу знаний и рисует последовательность стадий со статусами, таймингами и
 * раскрываемыми деталями (args / summary / dataRef) — SOTA #7 agent transparency.
 *
 * Backend: POST /api/v1/agent/reasoning-trace (routers/agent_reasoning.py).
 */

export interface ReasoningStep {
  stepIndex: number;
  tool: string;
  label: string;
  iconKey: 'done' | 'error' | 'running' | 'pending';
  status: string;
  duration_ms: number;
  offsetMs: number;
  summary: string;
  rationale: string;
  args: Record<string, unknown>;
  dataRef: string | null;
  error: string | null;
  detail: Record<string, unknown>;
}
export interface ReasoningTrace {
  question: string;
  intent: { intent: string; confidence: number; matched: string[] } | null;
  stages: { id: string; label: string }[];
  tokens: string[];
  steps: ReasoningStep[];
  totalDurationMs: number;
  statusCounts: Record<string, number>;
}

const STAGE_ICON: Record<string, typeof Crosshair> = {
  resolve: Crosshair,
  graph_query: Share2,
  vector_search: ScanSearch,
  evidence_check: ShieldCheck,
  gap_scan: TriangleAlert,
};

function StatusMark({ iconKey }: { iconKey: ReasoningStep['iconKey'] }) {
  if (iconKey === 'done') return <CheckCircle2 size={16} className="text-verified" />;
  if (iconKey === 'error') return <XCircle size={16} className="text-gap" />;
  if (iconKey === 'running') return <Loader2 size={16} className="animate-spin text-copper" />;
  return <Circle size={16} className="text-faint" />;
}

const EXAMPLES = [
  'Влияние старения Al-Cu сплава при 180°C 2ч на твёрдость',
  'Какие пробелы в данных по прочности титановых сплавов?',
  'Сравнить режимы термообработки для стали 40Х',
];

function StepRow({ step }: { step: ReasoningStep }) {
  const [open, setOpen] = useState(false);
  const Icon = STAGE_ICON[step.tool] ?? Cpu;
  return (
    <div className="relative pl-10">
      {/* rail dot */}
      <div className="absolute left-2.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-nickel/15 ring-2 ring-graphite">
        <StatusMark iconKey={step.iconKey} />
      </div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-nickel/10"
      >
        <Icon size={16} className="shrink-0 text-copper" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-ink">{step.label}</span>
            <code className="hidden shrink-0 rounded bg-ink/5 px-1 text-[11px] text-faint sm:inline">
              {step.tool}
            </code>
          </div>
          <div className="truncate text-xs text-muted">{step.summary}</div>
        </div>
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-faint">
          <Clock size={11} />
          {step.duration_ms} ms
        </span>
        <ChevronRight
          size={14}
          className={`shrink-0 text-faint transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>

      {open && (
        <div className="mb-1 ml-3 space-y-2 rounded-md border-l border-nickel/40 bg-ink/[0.03] px-4 py-3 text-xs">
          <p className="text-muted">{step.rationale}</p>
          {step.error && (
            <p className="rounded bg-gap/10 px-2 py-1 text-gap">error: {step.error}</p>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>
              <div className="eyebrow mb-1 text-faint">args</div>
              <pre className="overflow-x-auto rounded bg-ink/5 p-2 text-[11px] text-nickel">
                {JSON.stringify(step.args, null, 2)}
              </pre>
            </div>
            <div>
              <div className="eyebrow mb-1 text-faint">
                dataRef · {step.dataRef ?? '—'}
              </div>
              <pre className="max-h-52 overflow-auto rounded bg-ink/5 p-2 text-[11px] text-nickel">
                {JSON.stringify(step.detail, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function AgentReasoningTimelineView() {
  const [q, setQ] = useState('');
  const trace = useMutation({
    mutationFn: (question: string) => api.agentReasoningTrace(question),
  });
  const data = trace.data;

  const submit = (text: string) => {
    if (text.trim()) trace.mutate(text.trim());
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow text-copper">Как ассистент ищет ответ</div>
        <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
          Ход мысли ассистента
        </h2>
        <p className="mt-1 text-sm text-muted">
          Пошагово видно, как ассистент ищет ответ: что искали, что нашли и сколько это заняло.
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
              placeholder="Научный вопрос…"
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
              <span className="hidden sm:inline">Показать ход</span>
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
            Не удалось построить трассу. Попробуйте другой вопрос.
          </p>
        )}

        {/* Result */}
        {data && (
          <div className="mt-6">
            {/* Header: intent + totals */}
            <div className="flex flex-wrap items-center gap-2">
              {data.intent && (
                <span className="chip text-copper" title="Тип вопроса">
                  <Cpu size={12} className="mr-1 inline" />
                  {data.intent.intent} · {(data.intent.confidence * 100).toFixed(0)}%
                </span>
              )}
              <span className="chip text-muted">
                <Clock size={12} className="mr-1 inline" />
                {data.totalDurationMs} ms всего
              </span>
              <span className="chip text-verified">
                {data.statusCounts.ok ?? 0} ok
              </span>
              {(data.statusCounts.error ?? 0) > 0 && (
                <span className="chip text-gap">{data.statusCounts.error} error</span>
              )}
              {data.tokens.map((t) => (
                <span key={t} className="chip text-faint">
                  {t}
                </span>
              ))}
            </div>

            {/* Timeline rail */}
            <div className="relative mt-5">
              <div className="absolute left-[19px] top-2 bottom-2 w-px bg-nickel/25" />
              <div className="space-y-1">
                {data.steps.map((s) => (
                  <StepRow key={s.stepIndex} step={s} />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
