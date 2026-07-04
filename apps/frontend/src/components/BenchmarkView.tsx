import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Award, CircleCheck, CircleSlash, FlaskConical, Loader2, Play, Trophy } from 'lucide-react';

// §23.31 head-to-head benchmark UI. Self-contained (no api.ts edits): it calls the
// benchmark router directly with the same session-auth convention as api.ts.

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

interface SystemInfo {
  id: string;
  label: string;
  desc: string;
}
interface MetricInfo {
  id: string;
  label: string;
  higher_is_better: boolean;
}
interface ExternalEntry {
  system: string;
  repo: string;
  arxiv: string;
  recall_at_10: number;
  note: string;
}
interface SystemsResponse {
  systems: SystemInfo[];
  full_system: string;
  metrics: MetricInfo[];
  ablations: string[];
  external_leaderboard: ExternalEntry[];
}

interface MetricRow {
  metric: string;
  higher_is_better: boolean;
  scores: [string, number][];
  winner: string;
  full_delta: number;
}
interface Component {
  component: string;
  ablated_score: number;
  contribution: number;
}
interface ExternalRow {
  metric: string;
  ours: number;
  external: number;
  external_system: string;
  delta: number;
  beats: boolean;
}
interface BenchmarkResult {
  full_system: string;
  systems: Record<string, Record<string, number>>;
  benchmark: { metrics: MetricRow[]; full_wins: number; full_losses: number; verdict: string };
  ablation: { full_score: number; components: Component[]; most_important: string | null };
  external: {
    rows: ExternalRow[];
    n_beat: number;
    verdict: string;
    our_value: number;
    provenance: { system: string; repo: string; arxiv: string }[];
  };
  verdict: string;
  golden_size: number;
  k: number;
  report_path: string | null;
}

function fmt(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

const METRIC_LABEL: Record<string, string> = {
  recall_at_10: 'Recall@10',
  mrr: 'MRR',
  precision_at_10: 'Precision@10',
  citation_precision: 'Citation prec.',
  unsupported_rate: 'Unsupported↓',
  latency_ms: 'Latency ms↓',
};

export function BenchmarkView() {
  const [result, setResult] = useState<BenchmarkResult | null>(null);
  const info = useQuery({
    queryKey: ['benchmark-systems'],
    queryFn: () => apiGet<SystemsResponse>('/api/v1/benchmark/systems'),
  });
  const run = useMutation({
    mutationFn: () => apiPost<BenchmarkResult>('/api/v1/benchmark/run', { write_report: true }),
    onSuccess: (d) => setResult(d),
  });

  const systemIds = info.data?.systems.map((s) => s.id) ?? [];
  const labelOf = (id: string) => info.data?.systems.find((s) => s.id === id)?.label ?? id;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">baseline / ablation · §23.31</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Head-to-head бенчмарк</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Честное доказательство «SOTA цифрами»: полная система против plain-RAG (A), BM25 (B),
          Neo4j-structured (C) и GraphRAG-community (D) на golden-наборе — Recall@10, MRR,
          citation-precision, unsupported-rate, latency. Плюс leave-one-out абляции и сравнение с
          внешними лидербордами (LightRAG / HippoRAG2 / PathRAG / MS GraphRAG).
        </p>

        {/* Systems catalogue */}
        {info.data && (
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {info.data.systems.map((s) => (
              <div key={s.id} className="panel p-3">
                <div className="font-display text-sm text-ink">{s.label}</div>
                <div className="mt-1 text-xs text-faint">{s.desc}</div>
              </div>
            ))}
          </div>
        )}

        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="btn-copper mb-6 flex items-center gap-2"
        >
          {run.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {run.isPending ? 'Прогон бенчмарка…' : 'Запустить бенчмарк'}
        </button>

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
                result.verdict === 'sota' ? 'border-emerald-500/40' : 'border-amber-500/40'
              }`}
            >
              {result.verdict === 'sota' ? (
                <Trophy size={28} className="text-emerald-400" />
              ) : (
                <CircleSlash size={28} className="text-amber-400" />
              )}
              <div>
                <div className="font-display text-lg text-ink">
                  {result.verdict === 'sota' ? 'SOTA подтверждён' : 'Пока не SOTA'}
                </div>
                <div className="text-sm text-faint">
                  Полная система выигрывает {result.benchmark.full_wins} из{' '}
                  {result.benchmark.metrics.length} метрик (проигрывает {result.benchmark.full_losses})
                  на golden-наборе из {result.golden_size} запросов (k={result.k}).
                </div>
              </div>
            </div>

            {/* Systems × metrics winner table */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Award size={18} className="text-copper" /> Системы × метрики
              </h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Метрика</th>
                      {systemIds.map((id) => (
                        <th key={id} className="px-3 py-2 text-right" title={labelOf(id)}>
                          {id.replace(/_/g, ' ')}
                        </th>
                      ))}
                      <th className="px-3 py-2">Победитель</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.benchmark.metrics.map((m) => {
                      const scoreMap = Object.fromEntries(m.scores);
                      return (
                        <tr key={m.metric} className="border-b border-line/30">
                          <td className="px-3 py-2 text-ink">
                            {METRIC_LABEL[m.metric] ?? m.metric}
                          </td>
                          {systemIds.map((id) => {
                            const v = scoreMap[id];
                            const isWinner = id === m.winner;
                            return (
                              <td
                                key={id}
                                className={`px-3 py-2 text-right font-mono ${
                                  isWinner ? 'font-bold text-emerald-400' : 'text-faint'
                                }`}
                              >
                                {v === undefined ? '—' : fmt(v)}
                              </td>
                            );
                          })}
                          <td className="px-3 py-2 text-xs text-copper">
                            {m.winner.replace(/_/g, ' ')}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Ablation contributions */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <FlaskConical size={18} className="text-copper" /> Абляции (leave-one-out, §23.19)
              </h3>
              <div className="panel p-3">
                <div className="mb-2 text-xs text-faint">
                  Полная система Recall@10 = <span className="font-mono">{fmt(result.ablation.full_score)}</span>.
                  Вклад = сколько теряется без компонента (больше — важнее).
                </div>
                <div className="space-y-2">
                  {result.ablation.components.map((c) => {
                    const width = Math.min(100, Math.abs(c.contribution) * 400);
                    return (
                      <div key={c.component} className="flex items-center gap-2 text-sm">
                        <div className="w-56 text-ink">
                          {c.component.replace(/_/g, ' ')}
                          {result.ablation.most_important === c.component && (
                            <span className="ml-1 text-xs text-emerald-400">★</span>
                          )}
                        </div>
                        <div className="h-3 flex-1 rounded bg-void/40">
                          <div
                            className={`h-3 rounded ${
                              c.contribution >= 0 ? 'bg-copper' : 'bg-red-500/70'
                            }`}
                            style={{ width: `${width}%` }}
                          />
                        </div>
                        <div className="w-24 text-right font-mono text-xs text-faint">
                          {c.contribution >= 0 ? '+' : ''}
                          {fmt(c.contribution)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* External SOTA leaderboard */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Trophy size={18} className="text-copper" /> Внешний SOTA-лидерборд (§23.35)
              </h3>
              <div className="panel p-3">
                <div className="mb-2 text-sm text-faint">
                  Наш Recall@10 = <span className="font-mono text-ink">{fmt(result.external.our_value)}</span> —
                  вердикт{' '}
                  <span
                    className={
                      result.external.verdict === 'competitive'
                        ? 'text-emerald-400'
                        : 'text-amber-400'
                    }
                  >
                    {result.external.verdict}
                  </span>{' '}
                  (обошли/сравняли {result.external.n_beat} из {result.external.rows.length}).
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                        <th className="px-3 py-2">Система</th>
                        <th className="px-3 py-2">arXiv</th>
                        <th className="px-3 py-2 text-right">Reported R@10</th>
                        <th className="px-3 py-2 text-right">Δ</th>
                        <th className="px-3 py-2 text-center">Мы ≥</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.external.rows.map((r) => {
                        const prov = result.external.provenance.find(
                          (p) => p.system === r.external_system,
                        );
                        return (
                          <tr key={r.external_system} className="border-b border-line/30">
                            <td className="px-3 py-2 text-ink">
                              {r.external_system}
                              {prov && (
                                <span className="ml-2 font-mono text-[10px] text-faint">
                                  {prov.repo}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-faint">
                              {prov?.arxiv ?? ''}
                            </td>
                            <td className="px-3 py-2 text-right font-mono">{fmt(r.external)}</td>
                            <td
                              className={`px-3 py-2 text-right font-mono ${
                                r.delta >= 0 ? 'text-emerald-400' : 'text-amber-400'
                              }`}
                            >
                              {r.delta >= 0 ? '+' : ''}
                              {fmt(r.delta)}
                            </td>
                            <td className="px-3 py-2 text-center">
                              {r.beats ? (
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
                <div className="mt-2 text-[10px] text-faint">
                  Reference-числа из §23.35 (reported — валидировать при вендоринге, §23.33).
                </div>
              </div>
            </div>

            {result.report_path && (
              <div className="text-xs text-faint">
                Отчёт опубликован: <span className="font-mono text-ink">{result.report_path}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
