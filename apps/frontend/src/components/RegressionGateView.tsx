import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowDown,
  ArrowUp,
  CircleCheck,
  CircleSlash,
  Loader2,
  Minus,
  Play,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';

// §18.11 eval regression-gate UI. Self-contained (no api.ts edits): calls the
// regression-gate router directly with the same session-auth convention as api.ts.

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

interface SpecInfo {
  metric: string;
  label: string;
  category: string;
  higher_is_better: boolean;
  threshold: number;
  tol: number;
  live: boolean;
}
interface BaselineResponse {
  k: number;
  specs: SpecInfo[];
}

interface MetricRow {
  metric: string;
  label: string;
  category: string;
  higher_is_better: boolean;
  threshold: number;
  previous: number | null;
  current: number | null;
  delta: number | null;
  gate_pass: boolean;
  regressed: boolean;
  improved: boolean;
  status: string;
}
interface CategorySummary {
  category: string;
  total: number;
  passed: number;
  failed: number;
}
interface GateResult {
  verdict: string;
  exit_code: number;
  rows: MetricRow[];
  categories: CategorySummary[];
  failures: string[];
  regressions: string[];
  improvements: string[];
  generated_from: string;
  generated_at: string;
  markdown: string;
  html: string;
  run_id?: string;
  git_sha?: string;
  golden_size?: number;
  k?: number;
  elapsed_ms?: number;
  has_previous?: boolean;
  current_metrics?: Record<string, number>;
  previous_metrics?: Record<string, number> | null;
}

interface HistoryRun {
  run_id: string;
  generated_at: string;
  git_sha: string;
  verdict: string;
  exit_code: number;
  metrics: Record<string, number>;
}
interface HistoryResponse {
  count: number;
  runs: HistoryRun[];
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

function fmtDelta(v: number | null): string {
  if (v === null) return '—';
  const s = fmt(Math.abs(v));
  if (v > 0) return `+${s}`;
  if (v < 0) return `−${s}`;
  return '0';
}

const STATUS_STYLE: Record<string, string> = {
  missing: 'text-red-400',
  below_threshold: 'text-red-400',
  regressed: 'text-amber-400',
  improved: 'text-emerald-400',
  ok: 'text-faint',
  new: 'text-sky-400',
};
const STATUS_LABEL: Record<string, string> = {
  missing: 'нет данных',
  below_threshold: 'ниже порога',
  regressed: 'регрессия',
  improved: 'улучшение',
  ok: 'без изменений',
  new: 'новый',
};

function StatusPill({ row }: { row: MetricRow }) {
  const cls = STATUS_STYLE[row.status] ?? 'text-faint';
  const label = STATUS_LABEL[row.status] ?? row.status;
  return <span className={`text-xs font-medium ${cls}`}>{label}</span>;
}

function DeltaCell({ row }: { row: MetricRow }) {
  if (row.delta === null) return <span className="text-faint">—</span>;
  const positive = row.delta > 0;
  const better = row.improved;
  const worse = row.regressed;
  const cls = better ? 'text-emerald-400' : worse ? 'text-amber-400' : 'text-faint';
  const Icon = row.delta === 0 ? Minus : positive ? ArrowUp : ArrowDown;
  return (
    <span className={`inline-flex items-center gap-1 font-mono ${cls}`}>
      <Icon size={12} />
      {fmtDelta(row.delta)}
    </span>
  );
}

export function RegressionGateView() {
  const [result, setResult] = useState<GateResult | null>(null);

  const baseline = useQuery({
    queryKey: ['reg-gate-baseline'],
    queryFn: () => apiGet<BaselineResponse>('/api/v1/regression-gate/baseline'),
  });
  const history = useQuery({
    queryKey: ['reg-gate-history'],
    queryFn: () => apiGet<HistoryResponse>('/api/v1/regression-gate/history?limit=8'),
  });

  const run = useMutation({
    mutationFn: () =>
      apiPost<GateResult>('/api/v1/regression-gate/run', {
        dataset_version: 'seed',
        write_report: true,
      }),
    onSuccess: (d) => {
      setResult(d);
      history.refetch();
    },
  });

  const passed = result?.verdict === 'pass';

  // Group rows by category for the diff table.
  const grouped: Record<string, MetricRow[]> = {};
  for (const r of result?.rows ?? []) {
    (grouped[r.category] ??= []).push(r);
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">CI regression-gate · §18.11</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Регрессионный gate оценки</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          CI-ворота качества: живой прогон golden-набора над графом собирает §15.2-метрики
          (Recall@10 · MRR · nDCG · Precision@10 · citation-precision · unsupported-rate),
          сверяет их с baseline-порогами и предыдущим прогоном. Падение любой метрики ниже порога
          или регрессия относительно прошлого прогона роняет gate (exit-code ≠ 0). Ниже — сводка
          по категориям §15.1 и diff-таблица; Markdown/HTML-отчёт публикуется на сервере.
        </p>

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="btn-copper flex items-center gap-2"
          >
            {run.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {run.isPending ? 'Прогон gate…' : 'Запустить gate'}
          </button>
          {result?.run_id && (
            <a
              href="/api/v1/regression-gate/report"
              target="_blank"
              rel="noreferrer"
              className="text-sm text-copper underline-offset-2 hover:underline"
            >
              Открыть HTML-отчёт →
            </a>
          )}
          {baseline.data && (
            <span className="text-xs text-faint">
              baseline: {baseline.data.specs.filter((s) => s.live).length} живых метрик · k=
              {baseline.data.k}
            </span>
          )}
        </div>

        {run.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка прогона: {(run.error as Error).message}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* Verdict banner */}
            <div
              className={`panel flex items-center gap-3 p-4 ${
                passed ? 'border-emerald-500/40' : 'border-red-500/40'
              }`}
            >
              {passed ? (
                <CircleCheck size={28} className="text-emerald-400" />
              ) : (
                <CircleSlash size={28} className="text-red-400" />
              )}
              <div className="flex-1">
                <div className="font-display text-lg text-ink">
                  {passed ? 'PASS — регрессий нет' : 'FAIL — обнаружена регрессия'}
                  <span className="ml-2 text-sm text-faint">exit code {result.exit_code}</span>
                </div>
                <div className="text-sm text-faint">
                  {result.has_previous
                    ? 'Diff к предыдущему прогону из истории'
                    : 'Первый прогон — сравнение только с baseline-порогами'}
                  {result.golden_size !== undefined &&
                    ` · golden ${result.golden_size} запросов · k=${result.k}`}
                  {result.elapsed_ms !== undefined && ` · ${result.elapsed_ms} мс`}
                  {result.git_sha && ` · ${result.git_sha}`}
                </div>
              </div>
            </div>

            {/* Failures / regressions callout */}
            {(result.failures.length > 0 || result.improvements.length > 0) && (
              <div className="grid gap-3 sm:grid-cols-2">
                {result.failures.length > 0 && (
                  <div className="panel border-red-500/40 p-3">
                    <div className="mb-1 flex items-center gap-2 text-sm text-red-400">
                      <TriangleAlert size={15} /> Провалившиеся метрики
                    </div>
                    <div className="font-mono text-xs text-faint">
                      {result.failures.join(', ')}
                    </div>
                  </div>
                )}
                {result.improvements.length > 0 && (
                  <div className="panel border-emerald-500/40 p-3">
                    <div className="mb-1 flex items-center gap-2 text-sm text-emerald-400">
                      <ShieldCheck size={15} /> Улучшения
                    </div>
                    <div className="font-mono text-xs text-faint">
                      {result.improvements.join(', ')}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Category summary */}
            <div>
              <h3 className="mb-2 font-display text-lg">Сводка по категориям (§15.1)</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {result.categories.map((c) => (
                  <div key={c.category} className="panel p-3">
                    <div className="text-xs text-faint">{c.category}</div>
                    <div className="mt-1 font-display text-lg text-ink">
                      {c.passed}/{c.total}
                    </div>
                    <div
                      className={`text-xs ${c.failed === 0 ? 'text-emerald-400' : 'text-red-400'}`}
                    >
                      {c.failed === 0 ? 'все прошли' : `провалов: ${c.failed}`}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Metric diff table */}
            <div>
              <h3 className="mb-2 font-display text-lg">Diff метрик (§15.2)</h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Метрика</th>
                      <th className="px-3 py-2 text-right">Порог</th>
                      <th className="px-3 py-2 text-right">Прошлое</th>
                      <th className="px-3 py-2 text-right">Текущее</th>
                      <th className="px-3 py-2 text-right">Δ</th>
                      <th className="px-3 py-2">Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(grouped).map(([cat, rows]) => (
                      <>
                        <tr key={`h-${cat}`} className="bg-line/10">
                          <td
                            colSpan={6}
                            className="px-3 py-1 text-xs font-semibold uppercase text-faint"
                          >
                            {cat}
                          </td>
                        </tr>
                        {rows.map((r) => (
                          <tr key={r.metric} className="border-b border-line/30">
                            <td className="px-3 py-2 text-ink">
                              {r.label}{' '}
                              <span className="text-faint">{r.higher_is_better ? '↑' : '↓'}</span>
                            </td>
                            <td className="px-3 py-2 text-right font-mono text-faint">
                              {fmt(r.threshold)}
                            </td>
                            <td className="px-3 py-2 text-right font-mono text-faint">
                              {fmt(r.previous)}
                            </td>
                            <td
                              className={`px-3 py-2 text-right font-mono ${
                                r.gate_pass ? 'text-ink' : 'font-bold text-red-400'
                              }`}
                            >
                              {fmt(r.current)}
                            </td>
                            <td className="px-3 py-2 text-right">
                              <DeltaCell row={r} />
                            </td>
                            <td className="px-3 py-2">
                              <StatusPill row={r} />
                            </td>
                          </tr>
                        ))}
                      </>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Run history */}
            {history.data && history.data.runs.length > 0 && (
              <div>
                <h3 className="mb-2 font-display text-lg">История прогонов</h3>
                <div className="panel overflow-x-auto p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                        <th className="px-3 py-2">Прогон</th>
                        <th className="px-3 py-2">git</th>
                        <th className="px-3 py-2">Вердикт</th>
                        <th className="px-3 py-2 text-right">Recall@10</th>
                        <th className="px-3 py-2 text-right">MRR</th>
                        <th className="px-3 py-2 text-right">Citation</th>
                        <th className="px-3 py-2 text-right">Unsup↓</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.data.runs.map((h) => (
                        <tr key={h.run_id} className="border-b border-line/30">
                          <td className="px-3 py-2 font-mono text-xs text-faint">{h.run_id}</td>
                          <td className="px-3 py-2 font-mono text-xs text-faint">{h.git_sha}</td>
                          <td className="px-3 py-2">
                            <span
                              className={
                                h.verdict === 'pass' ? 'text-emerald-400' : 'text-red-400'
                              }
                            >
                              {h.verdict === 'pass' ? 'PASS' : 'FAIL'}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-faint">
                            {fmt(h.metrics?.recall_at_10)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-faint">
                            {fmt(h.metrics?.mrr)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-faint">
                            {fmt(h.metrics?.citation_precision)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-faint">
                            {fmt(h.metrics?.unsupported_rate)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
