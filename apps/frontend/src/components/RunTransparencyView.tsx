import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowRight,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  ChevronRight,
  Clock,
  Cpu,
  Database,
  Hash,
  ShieldCheck,
  ShieldAlert,
  Copy,
  Check,
  Repeat2,
  FileCode2,
} from 'lucide-react';
import { api } from '../api';

/**
 * §13.23 — Панель прозрачности и воспроизводимости прогона.
 *
 * Показывает, КАК агент рассуждал, и ДОКАЗЫВАЕТ, что это воспроизводимо:
 *   1. tool_trace  — журнал вызовов инструментов (tool, args, статус, длительность);
 *   2. сгенерированный Cypher — для каждой стадии точный запрос + связанные параметры,
 *      что реально исполнились по живому графу (Neo4j :8000);
 *   3. детерминированный replay (seed) — по seed минтуется стабильный trace_id; план
 *      исполняется дважды, дайджесты контента сравниваются: reproducible=true ⇔ второй
 *      прогон дал тот же контент (Cypher + параметры + идентичность строк).
 *
 * Backend: POST /api/v1/agent/run-transparency (routers/run_transparency.py).
 */

// ---- API shape ------------------------------------------------------------
export interface RunPhase {
  phase: string;
  tool: string;
  label: string;
  rationale: string;
  status: 'ok' | 'error';
  iconKey: 'done' | 'error';
  offsetMs: number;
  durationMs: number;
  cypher: string;
  params: Record<string, unknown>;
  rowCount: number;
  summary: string;
  error?: string | null;
  result: Record<string, unknown>;
  resultSignature: string[];
}

export interface ToolTraceRow {
  tool: string;
  args: Record<string, unknown>;
  started_at: number;
  finished_at: number;
  duration_ms: number;
  status: string;
  summary: string;
  dataRef?: string | null;
  error?: string | null;
}

export interface RunTransparency {
  question: string;
  seed: string;
  traceId: string;
  rootSpanId: string;
  traceparent: string;
  tokens: string[];
  phases: RunPhase[];
  toolTrace: ToolTraceRow[];
  phaseCount: number;
  statusCounts: Record<string, number>;
  totalDurationMs: number;
  promptPins: { versions: Record<string, string>; fingerprint: string };
  runDigest: string;
  replay: { seed: string; digest: string; reproducible: boolean; note: string };
}

const EXAMPLES = [
  'Влияние старения Al-Cu сплава при 180°C 2ч на твёрдость',
  'Какие пробелы в данных по прочности титановых сплавов?',
  'Сравнить режимы термообработки для стали 40Х',
];

function StatusMark({ iconKey }: { iconKey: 'done' | 'error' }) {
  if (iconKey === 'done') return <CheckCircle2 size={16} className="text-verified" />;
  if (iconKey === 'error') return <XCircle size={16} className="text-gap" />;
  return <Circle size={16} className="text-faint" />;
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
      className="flex items-center gap-1 text-[11px] text-faint transition-colors hover:text-nickel"
      title="Скопировать"
    >
      {done ? <Check size={11} /> : <Copy size={11} />}
      {label && <span>{label}</span>}
    </button>
  );
}

function PhaseCard({ step, index }: { step: RunPhase; index: number }) {
  const [open, setOpen] = useState(index === 0);
  return (
    <div className="relative pl-10">
      <div className="absolute left-2.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-nickel/15 ring-2 ring-graphite">
        <StatusMark iconKey={step.iconKey} />
      </div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-nickel/10"
      >
        <FileCode2 size={16} className="shrink-0 text-copper" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-ink">{step.label}</span>
            <code className="hidden shrink-0 rounded bg-ink/5 px-1 text-[11px] text-faint sm:inline">
              {step.tool}
            </code>
          </div>
          <div className="truncate text-xs text-muted">{step.summary}</div>
        </div>
        <span className="hidden shrink-0 items-center gap-1 text-[11px] text-faint sm:flex">
          <Database size={11} />
          {step.rowCount} строк
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-faint">
          <Clock size={11} />
          {step.durationMs} ms
        </span>
        <ChevronRight
          size={14}
          className={`shrink-0 text-faint transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>

      {open && (
        <div className="mb-1 ml-3 space-y-3 rounded-md border-l border-nickel/40 bg-ink/[0.03] px-4 py-3 text-xs">
          <p className="text-muted">{step.rationale}</p>
          {step.error && (
            <p className="rounded bg-gap/10 px-2 py-1 text-gap">error: {step.error}</p>
          )}

          {/* Generated Cypher — the exact executed query */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <div className="eyebrow text-faint">сгенерированный Cypher</div>
              <CopyButton text={step.cypher} label="copy" />
            </div>
            <pre className="overflow-x-auto rounded bg-ink/[0.06] p-2.5 text-[11px] leading-relaxed text-nickel">
              {step.cypher}
            </pre>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <div className="eyebrow mb-1 text-faint">параметры (bound)</div>
              <pre className="overflow-x-auto rounded bg-ink/5 p-2 text-[11px] text-nickel">
                {JSON.stringify(step.params, null, 2)}
              </pre>
            </div>
            <div>
              <div className="eyebrow mb-1 text-faint">результат ({step.rowCount})</div>
              <pre className="max-h-52 overflow-auto rounded bg-ink/5 p-2 text-[11px] text-nickel">
                {JSON.stringify(step.result, null, 2)}
              </pre>
            </div>
          </div>

          <div>
            <div className="eyebrow mb-1 text-faint">
              сигнатура результата · {step.resultSignature.length} ключ(ей) — входит в дайджест
            </div>
            <div className="flex flex-wrap gap-1">
              {step.resultSignature.slice(0, 24).map((s) => (
                <code key={s} className="rounded bg-ink/5 px-1 py-0.5 text-[10px] text-faint">
                  {s}
                </code>
              ))}
              {step.resultSignature.length > 24 && (
                <span className="text-[10px] text-faint">
                  +{step.resultSignature.length - 24}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function RunTransparencyView() {
  const [q, setQ] = useState('');
  const [seed, setSeed] = useState('0');
  const run = useMutation({
    mutationFn: (vars: { question: string; seed: string }) =>
      api.runTransparency(vars.question, vars.seed),
  });
  const data = run.data;

  const submit = (text: string) => {
    if (text.trim()) run.mutate({ question: text.trim(), seed: seed.trim() || '0' });
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow text-copper">Проверяемость и воспроизводимость</div>
        <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
          Прозрачность и воспроизводимость прогона
        </h2>
        <p className="mt-1 text-sm text-muted">
          Виден каждый шаг ответа и его источник. Один и тот же запрос повторяется дважды и даёт идентичный результат — это доказывает воспроизводимость.
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
              disabled={run.isPending || !q.trim()}
              className="btn-copper mb-1 mr-1 flex items-center gap-1.5"
            >
              {run.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              <span className="hidden sm:inline">Прогнать</span>
            </button>
          </div>
          <div className="flex items-center gap-2 border-t border-nickel/20 px-3 py-1.5">
            <Hash size={12} className="text-faint" />
            <label className="text-[11px] text-faint">seed</label>
            <input
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              className="w-28 rounded bg-ink/5 px-2 py-0.5 text-[12px] text-ink focus:outline-none"
              placeholder="0"
            />
            <span className="text-[11px] text-faint">
              один seed + вопрос → один trace_id (детерминированно)
            </span>
          </div>
        </div>

        {/* Example prompts */}
        {!data && !run.isPending && (
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

        {run.isError && (
          <p className="mt-4 rounded-md bg-gap/10 px-3 py-2 text-sm text-gap">
            Не удалось построить прогон. Попробуйте другой вопрос.
          </p>
        )}

        {/* Result */}
        {data && (
          <div className="mt-6">
            {/* Reproducibility banner */}
            <div
              className={`panel flex flex-col gap-2 p-4 ${
                data.replay.reproducible ? 'ring-1 ring-verified/40' : 'ring-1 ring-gap/40'
              }`}
            >
              <div className="flex items-center gap-2">
                {data.replay.reproducible ? (
                  <ShieldCheck size={18} className="text-verified" />
                ) : (
                  <ShieldAlert size={18} className="text-gap" />
                )}
                <span className="text-sm font-semibold text-ink">
                  {data.replay.reproducible
                    ? 'Прогон воспроизводим'
                    : 'Прогон не воспроизводим'}
                </span>
                <span className="ml-auto flex items-center gap-1 text-[11px] text-faint">
                  <Repeat2 size={12} />
                  replay ×2
                </span>
              </div>
              <p className="text-xs text-muted">{data.replay.note}</p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div className="flex items-center justify-between rounded bg-ink/5 px-2 py-1">
                  <span className="text-[11px] text-faint">runDigest</span>
                  <span className="flex items-center gap-2">
                    <code className="text-[11px] text-nickel">
                      {data.runDigest.slice(0, 16)}…
                    </code>
                    <CopyButton text={data.runDigest} />
                  </span>
                </div>
                <div className="flex items-center justify-between rounded bg-ink/5 px-2 py-1">
                  <span className="text-[11px] text-faint">replayDigest</span>
                  <span className="flex items-center gap-2">
                    <code className="text-[11px] text-nickel">
                      {data.replay.digest.slice(0, 16)}…
                    </code>
                    <CopyButton text={data.replay.digest} />
                  </span>
                </div>
              </div>
            </div>

            {/* Header chips: trace + prompt pins + totals */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="chip text-copper" title="Детерминированный trace_id (seed)">
                <Hash size={12} className="mr-1 inline" />
                trace {data.traceId.slice(0, 12)}…
              </span>
              <span className="chip text-muted">seed · {data.seed}</span>
              <span className="chip text-muted">
                <Clock size={12} className="mr-1 inline" />
                {data.totalDurationMs} ms
              </span>
              <span className="chip text-verified">{data.statusCounts.ok ?? 0} ok</span>
              {(data.statusCounts.error ?? 0) > 0 && (
                <span className="chip text-gap">{data.statusCounts.error} error</span>
              )}
              {data.promptPins.fingerprint && (
                <span
                  className="chip text-muted"
                  title={`Версии промптов: ${JSON.stringify(data.promptPins.versions)}`}
                >
                  <Cpu size={12} className="mr-1 inline" />
                  prompts {data.promptPins.fingerprint.slice(0, 8)}…
                </span>
              )}
            </div>

            {/* Tokens */}
            {data.tokens.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1">
                <span className="text-[11px] text-faint">токены:</span>
                {data.tokens.map((t) => (
                  <code key={t} className="rounded bg-ink/5 px-1 py-0.5 text-[11px] text-nickel">
                    {t}
                  </code>
                ))}
              </div>
            )}

            {/* Phase timeline with generated Cypher */}
            <div className="mt-5">
              <div className="eyebrow mb-2 text-faint">Стадии прогона · точные запросы к графу</div>
              <div className="relative space-y-1 before:absolute before:left-[19px] before:top-2 before:bottom-2 before:w-px before:bg-nickel/25">
                {data.phases.map((p, i) => (
                  <PhaseCard key={p.phase} step={p} index={i} />
                ))}
              </div>
            </div>

            {/* tool_trace table */}
            <div className="mt-6">
              <div className="eyebrow mb-2 text-faint">Журнал шагов</div>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-nickel/20 text-[11px] text-faint">
                    <tr>
                      <th className="px-3 py-2">#</th>
                      <th className="px-3 py-2">tool</th>
                      <th className="px-3 py-2">статус</th>
                      <th className="px-3 py-2">длит.</th>
                      <th className="px-3 py-2">итог</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.toolTrace.map((row, i) => (
                      <tr key={i} className="border-b border-nickel/10 last:border-0">
                        <td className="px-3 py-2 text-faint">{i}</td>
                        <td className="px-3 py-2">
                          <code className="text-nickel">{row.tool}</code>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={
                              row.status === 'ok' ? 'text-verified' : 'text-gap'
                            }
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-faint">{row.duration_ms} ms</td>
                        <td className="px-3 py-2 text-muted">{row.summary}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
