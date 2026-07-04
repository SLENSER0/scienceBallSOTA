import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Boxes,
  Brain,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  Loader2,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';

// §17.7 — Tool-call timeline of the scientific agent (SOTA #7 «agent transparency»).
// Shows HOW the agent thinks step-by-step for a question: resolved entities → graph
// query → vector search → evidence check → gap scan. The plan is REAL — the backend
// reuses the §13.8 intent classifier + §13.10 tool planner — and this component
// animates the planned tools pending→running→done so the user watches the agent reason.

// -- backend contract (POST /api/v1/agent/timeline) ---------------------------
type StageId = 'resolve' | 'graph' | 'vector' | 'evidence' | 'gap';

interface TimelineStep {
  stepIndex: number;
  tool: string;
  stage: StageId;
  label: string;
  rationale: string;
  status: string;
}
interface TimelineResponse {
  question: string;
  intent: string;
  confidence: number;
  matched: string[];
  parallel: boolean;
  stages: { id: StageId; label: string }[];
  steps: TimelineStep[];
}

// Local run status the UI animates through (independent of the backend `status`).
type RunStatus = 'pending' | 'running' | 'done';

const STAGE_ICON: Record<StageId, typeof Boxes> = {
  resolve: Boxes,
  graph: Network,
  vector: Search,
  evidence: ShieldCheck,
  gap: TriangleAlert,
};
const STAGE_TONE: Record<StageId, string> = {
  resolve: '#B9CAD4', // nickel bright
  graph: '#C87941', // copper
  vector: '#6C8CD5', // foreign blue
  evidence: '#3FB68B', // verified green
  gap: '#E0A23C', // gap amber
};

const INTENT_RU: Record<string, string> = {
  material_regime_property_query: 'материал + режим + свойство',
  entity_exploration: 'исследование сущности',
  experiment_lookup: 'поиск экспериментов',
  evidence_request: 'запрос доказательств',
  gap_analysis: 'анализ пробелов',
  contradiction_analysis: 'анализ противоречий',
  method_comparison: 'сравнение методов',
  literature_summary: 'обзор литературы',
  schema_help: 'справка по схеме',
};

const EXAMPLES = [
  'Как влияет старение при 180°C 2ч на твёрдость Al-Cu сплава 2024?',
  'Сравни отечественную и зарубежную практику флотации меди',
  'Какие пробелы в данных по коррозии никелевых сплавов?',
];

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

const STEP_MS = 520; // per-step «running» dwell for the reasoning animation

export function ToolTimeline({ question: initial }: { question?: string } = {}) {
  const [q, setQ] = useState(initial ?? '');
  const [plan, setPlan] = useState<TimelineResponse | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus[]>([]);
  const [active, setActive] = useState<number>(-1); // -1 idle, steps.length done
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const timers = useRef<number[]>([]);

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const run = useCallback(async (question: string) => {
    const text = question.trim();
    if (!text) return;
    clearTimers();
    setLoading(true);
    setError('');
    setPlan(null);
    setRunStatus([]);
    setActive(-1);
    setExpanded(null);
    try {
      const res = await fetch('/api/v1/agent/timeline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ question: text }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = (await res.json()) as TimelineResponse;
      setPlan(data);
      setRunStatus(data.steps.map(() => 'pending'));
      // Animate the agent «thinking»: each step running → done, in sequence.
      data.steps.forEach((_, i) => {
        timers.current.push(
          window.setTimeout(() => {
            setActive(i);
            setRunStatus((prev) => prev.map((s, j) => (j === i ? 'running' : s)));
          }, i * STEP_MS),
        );
        timers.current.push(
          window.setTimeout(() => {
            setRunStatus((prev) => prev.map((s, j) => (j === i ? 'done' : s)));
            if (i === data.steps.length - 1) setActive(data.steps.length);
          }, i * STEP_MS + STEP_MS - 60),
        );
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось построить таймлайн');
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-run when embedded with a fixed question (e.g. from the chat composer).
  useEffect(() => {
    if (initial && initial.trim()) {
      setQ(initial);
      run(initial);
    }
    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const embedded = initial !== undefined;

  return (
    <div className={embedded ? '' : 'mx-auto flex h-full max-w-3xl flex-col gap-5 p-6'}>
      {!embedded && (
        <header className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-copper/15 text-copper">
            <Brain className="h-5 w-5" />
          </div>
          <div>
            <h1 className="font-display text-lg text-ink">Как думает агент</h1>
            <p className="text-sm text-muted">
              Таймлайн вызовов инструментов — агент не просто ищет, он рассуждает по шагам:
              сущности → граф → вектор → доказательства → пробелы.
            </p>
          </div>
        </header>
      )}

      {!embedded && (
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && run(q)}
              placeholder="Задайте научный вопрос…"
              className="flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
            />
            <button
              onClick={() => run(q)}
              disabled={loading || !q.trim()}
              className="flex items-center gap-1.5 rounded-md bg-copper px-3.5 py-2 text-sm font-medium text-void transition hover:bg-copper-bright disabled:opacity-40"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Показать
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setQ(ex);
                  run(ex);
                }}
                className="rounded-full border border-line bg-surface/50 px-2.5 py-1 text-xs text-muted transition hover:border-copper/40 hover:text-ink"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
          {error}
        </div>
      )}

      {plan && (
        <div className="flex flex-col gap-4">
          {/* Intent header — why the agent chose this plan */}
          <div className="rounded-md border border-line bg-surface/60 p-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-faint">Интент</span>
              <span className="rounded-full bg-copper/15 px-2.5 py-0.5 text-sm font-medium text-copper">
                {INTENT_RU[plan.intent] ?? plan.intent}
              </span>
              {plan.parallel && (
                <span className="rounded-full border border-foreign/40 px-2 py-0.5 text-xs text-foreign">
                  параллельно
                </span>
              )}
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs text-faint">уверенность</span>
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
                  <div
                    className="h-full rounded-full bg-verified transition-all"
                    style={{ width: `${Math.round(plan.confidence * 100)}%` }}
                  />
                </div>
                <span className="font-mono text-xs text-muted">
                  {Math.round(plan.confidence * 100)}%
                </span>
              </div>
            </div>
            {plan.matched.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {plan.matched.slice(0, 6).map((m, i) => (
                  <span
                    key={i}
                    className="rounded border border-line bg-graphite px-1.5 py-0.5 font-mono text-[11px] text-faint"
                  >
                    {m.includes(':') ? m.split(':')[1] : m}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Vertical animated timeline */}
          <ol className="relative flex flex-col">
            {plan.steps.map((step, i) => {
              const st = runStatus[i] ?? 'pending';
              const Icon = STAGE_ICON[step.stage];
              const tone = STAGE_TONE[step.stage];
              const isLast = i === plan.steps.length - 1;
              const open = expanded === i;
              return (
                <li key={i} className="relative flex gap-3 pb-1">
                  {/* connector rail */}
                  {!isLast && (
                    <span
                      className="absolute left-[15px] top-8 h-[calc(100%-14px)] w-px"
                      style={{
                        background:
                          st === 'done'
                            ? tone
                            : 'linear-gradient(to bottom, #2A313E, transparent)',
                        opacity: st === 'done' ? 0.5 : 1,
                      }}
                    />
                  )}
                  {/* status node */}
                  <div
                    className="relative z-10 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-all"
                    style={{
                      borderColor: st === 'pending' ? '#2A313E' : tone,
                      background: st === 'done' ? `${tone}22` : '#12151C',
                      boxShadow: st === 'running' ? `0 0 0 4px ${tone}22` : 'none',
                    }}
                  >
                    {st === 'running' ? (
                      <Loader2 className="h-4 w-4 animate-spin" style={{ color: tone }} />
                    ) : st === 'done' ? (
                      <CircleCheck className="h-4 w-4" style={{ color: tone }} />
                    ) : (
                      <CircleDashed className="h-4 w-4 text-faint" />
                    )}
                  </div>
                  {/* step card */}
                  <button
                    onClick={() => setExpanded(open ? null : i)}
                    className="mb-1 mt-0.5 flex flex-1 flex-col rounded-md border border-line bg-surface/40 px-3 py-2 text-left transition hover:border-copper/30"
                    style={{ opacity: st === 'pending' ? 0.55 : 1 }}
                  >
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 shrink-0" style={{ color: tone }} />
                      <span className="text-sm font-medium text-ink">{step.label}</span>
                      <code className="rounded bg-graphite px-1.5 py-0.5 font-mono text-[11px] text-faint">
                        {step.tool}
                      </code>
                      {st === 'running' && (
                        <span className="text-xs text-muted">выполняется…</span>
                      )}
                      <ChevronRight
                        className={`ml-auto h-4 w-4 text-faint transition-transform ${
                          open ? 'rotate-90' : ''
                        }`}
                      />
                    </div>
                    {open && (
                      <p className="mt-1.5 border-t border-line/60 pt-1.5 text-xs leading-relaxed text-muted">
                        {step.rationale}
                      </p>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>

          {active >= plan.steps.length && (
            <div className="flex items-center gap-2 rounded-md border border-verified/30 bg-verified/10 px-3 py-2 text-sm text-verified">
              <CircleCheck className="h-4 w-4" />
              Агент завершил {plan.steps.length}{' '}
              {plan.steps.length === 1 ? 'шаг' : 'шага(ов)' } — ответ основан на доказательствах.
            </div>
          )}
        </div>
      )}

      {!plan && !loading && !error && !embedded && (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-faint">
          <Brain className="h-8 w-8 opacity-40" />
          <p className="text-sm">Задайте вопрос — увидите план рассуждения агента по шагам.</p>
        </div>
      )}
    </div>
  );
}
