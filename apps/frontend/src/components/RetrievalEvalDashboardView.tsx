import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CircleCheck, CircleSlash, Gauge, Loader2, Play, Trophy, Zap } from 'lucide-react';

// §4.11 retrieval-eval dashboard. Self-contained (no api.ts edits): calls the
// retrieval-eval router directly with the same session-auth convention as api.ts.
// Proves with numbers that hybrid+rerank beats single backends (bm25 / dense) on
// Recall@10 / MRR / nDCG@10 over the golden set.

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

interface BackendInfo {
  id: string;
  label: string;
  desc: string;
}
interface MetricInfo {
  id: string;
  label: string;
  higher_is_better: boolean;
}
interface GoldenEntry {
  query: string;
  relevant_ids: string[];
  n_relevant: number;
}
interface ConfigResponse {
  k: number;
  backends: BackendInfo[];
  metrics: MetricInfo[];
  verdict_metrics: string[];
  golden: GoldenEntry[];
  golden_size: number;
  dense_index_ready: boolean;
  mmr_lambda: number;
}

interface MatrixRow {
  backend: string;
  backend_label: string;
  rerank: boolean;
  metrics: Record<string, number>;
}
interface VerdictMetric {
  metric: string;
  champion: number;
  best_single: number;
  best_single_from: string;
  delta: number;
  wins: boolean;
}
interface RunResult {
  k: number;
  golden_size: number;
  backends: BackendInfo[];
  metrics: MetricInfo[];
  rerank_evaluated: boolean;
  matrix: MatrixRow[];
  verdict: { champion: string; passes: boolean; per_metric: VerdictMetric[] };
  dense_degraded_to_keyword: boolean;
  elapsed_ms: number;
}

function fmt(v: number): string {
  if (v === undefined || v === null) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

export function RetrievalEvalDashboardView() {
  const [result, setResult] = useState<RunResult | null>(null);
  const cfg = useQuery({
    queryKey: ['retrieval-eval-config'],
    queryFn: () => apiGet<ConfigResponse>('/api/v1/retrieval-eval/config'),
  });
  const run = useMutation({
    mutationFn: () => apiPost<RunResult>('/api/v1/retrieval-eval/run', { rerank: true }),
    onSuccess: (d) => setResult(d),
  });

  const metrics = result?.metrics ?? cfg.data?.metrics ?? [];
  // Champion cell = hybrid with rerank on (highlighted for a per-column win read).
  const isChampion = (r: MatrixRow) => r.backend === 'hybrid' && r.rerank;
  // Per-metric best value across the whole matrix (to bold the column leader).
  const bestByMetric: Record<string, number> = {};
  for (const r of result?.matrix ?? []) {
    for (const m of metrics) {
      const v = r.metrics[m.id];
      if (v !== undefined && (bestByMetric[m.id] === undefined || v > bestByMetric[m.id])) {
        bestByMetric[m.id] = v;
      }
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">retrieval-eval · §4.11</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Дашборд качества поиска
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Материализует качество retrieval числами: три бэкенда (BM25, dense, hybrid) × rerank
          off/on прогоняются по golden-набору над живым графом — Recall@10, MRR, nDCG@10,
          Precision@10, hit@10. Вердикт: гибрид с финальным rerank-проходом (§12.9 MMR) не ниже
          каждого одиночного бэкенда на acceptance-метриках §4.11.
        </p>

        {/* Backend catalogue */}
        {cfg.data && (
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            {cfg.data.backends.map((b) => (
              <div key={b.id} className="panel p-3">
                <div className="font-display text-sm text-ink">{b.label}</div>
                <div className="mt-1 text-xs text-faint">{b.desc}</div>
              </div>
            ))}
          </div>
        )}

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="btn-copper flex items-center gap-2"
          >
            {run.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            {run.isPending ? 'Прогон eval…' : 'Запустить eval'}
          </button>
          {cfg.data && (
            <span className="text-xs text-faint">
              golden: {cfg.data.golden_size} запросов · k={cfg.data.k} · dense-индекс:{' '}
              {cfg.data.dense_index_ready ? (
                <span className="text-emerald-400">готов</span>
              ) : (
                <span className="text-amber-400">пуст → keyword-деградация</span>
              )}
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
                result.verdict.passes ? 'border-emerald-500/40' : 'border-amber-500/40'
              }`}
            >
              {result.verdict.passes ? (
                <Trophy size={28} className="text-emerald-400" />
              ) : (
                <CircleSlash size={28} className="text-amber-400" />
              )}
              <div>
                <div className="font-display text-lg text-ink">
                  {result.verdict.passes
                    ? 'Hybrid + rerank выигрывает'
                    : 'Hybrid + rerank пока не доминирует'}
                </div>
                <div className="text-sm text-faint">
                  {result.verdict.champion} не ниже одиночных бэкендов на{' '}
                  {result.verdict.per_metric.filter((m) => m.wins).length} из{' '}
                  {result.verdict.per_metric.length} acceptance-метрик · golden={result.golden_size} ·
                  k={result.k} · {fmt(result.elapsed_ms)} мс
                </div>
              </div>
            </div>

            {/* Backend × rerank × metric matrix */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Gauge size={18} className="text-copper" /> Бэкенды × rerank × метрики
              </h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Бэкенд</th>
                      <th className="px-3 py-2">Rerank</th>
                      {metrics.map((m) => (
                        <th key={m.id} className="px-3 py-2 text-right">
                          {m.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.matrix.map((r) => (
                      <tr
                        key={`${r.backend}-${r.rerank}`}
                        className={`border-b border-line/30 ${
                          isChampion(r) ? 'bg-emerald-500/5' : ''
                        }`}
                      >
                        <td className="px-3 py-2 text-ink">{r.backend_label}</td>
                        <td className="px-3 py-2">
                          {r.rerank ? (
                            <span className="flex items-center gap-1 text-xs text-copper">
                              <Zap size={12} /> on
                            </span>
                          ) : (
                            <span className="text-xs text-faint">off</span>
                          )}
                        </td>
                        {metrics.map((m) => {
                          const v = r.metrics[m.id];
                          const isBest = v !== undefined && v === bestByMetric[m.id];
                          return (
                            <td
                              key={m.id}
                              className={`px-3 py-2 text-right font-mono ${
                                isBest ? 'font-bold text-emerald-400' : 'text-faint'
                              }`}
                            >
                              {fmt(v)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.dense_degraded_to_keyword && (
                <div className="mt-2 text-[11px] text-amber-400/80">
                  Dense-бэкенд деградировал к keyword-порядку (entity-индекс пуст) — честно
                  отражено в числах.
                </div>
              )}
            </div>

            {/* Acceptance verdict per metric */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Trophy size={18} className="text-copper" /> Вердикт §4.11 (champion vs лучший
                одиночный)
              </h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Метрика</th>
                      <th className="px-3 py-2 text-right">Hybrid + rerank</th>
                      <th className="px-3 py-2 text-right">Лучший одиночный</th>
                      <th className="px-3 py-2">Откуда</th>
                      <th className="px-3 py-2 text-right">Δ</th>
                      <th className="px-3 py-2 text-center">≥</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.verdict.per_metric.map((pm) => {
                      const label =
                        metrics.find((m) => m.id === pm.metric)?.label ?? pm.metric;
                      return (
                        <tr key={pm.metric} className="border-b border-line/30">
                          <td className="px-3 py-2 text-ink">{label}</td>
                          <td className="px-3 py-2 text-right font-mono text-emerald-400">
                            {fmt(pm.champion)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-faint">
                            {fmt(pm.best_single)}
                          </td>
                          <td className="px-3 py-2 text-xs text-faint">
                            {pm.best_single_from.replace(/_/g, ' ')}
                          </td>
                          <td
                            className={`px-3 py-2 text-right font-mono ${
                              pm.delta >= 0 ? 'text-emerald-400' : 'text-amber-400'
                            }`}
                          >
                            {pm.delta >= 0 ? '+' : ''}
                            {fmt(pm.delta)}
                          </td>
                          <td className="px-3 py-2 text-center">
                            {pm.wins ? (
                              <CircleCheck size={16} className="mx-auto text-emerald-400" />
                            ) : (
                              <CircleSlash size={16} className="mx-auto text-amber-400" />
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Golden set preview (before first run) */}
        {!result && cfg.data && (
          <div className="mt-4">
            <h3 className="mb-2 font-display text-sm text-faint">
              Golden-набор ({cfg.data.golden_size} запросов)
            </h3>
            <div className="panel p-3">
              <ul className="space-y-1 text-sm">
                {cfg.data.golden.map((g) => (
                  <li key={g.query} className="flex items-center gap-2">
                    <span className="text-ink">«{g.query}»</span>
                    <span className="text-xs text-faint">
                      → {g.n_relevant} релевант. id
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
