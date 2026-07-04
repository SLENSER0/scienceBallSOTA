import { useQuery } from '@tanstack/react-query';
import {
  Boxes,
  CircleCheck,
  GitMerge,
  Loader2,
  Lock,
  RefreshCw,
  ShieldCheck,
  SplitSquareHorizontal,
} from 'lucide-react';

// §8.13 ER observability. Self-contained (no api.ts edits): calls the
// er-metrics router directly with the same session-auth convention as api.ts.

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

interface ERTypeMetrics {
  entity_type: string;
  n_input: number;
  candidates_total: number;
  auto_merge_total: number;
  review_needed_total: number;
  separate_total: number;
  blocked_overwrite_total: number;
  backend: string;
}

interface ERMetricsResponse {
  er_candidates_total: number;
  er_auto_merge_total: number;
  er_review_needed_total: number;
  er_separate_total: number;
  er_blocked_overwrite_total: number;
  er_model_version: string;
  er_random_seed: number;
  er_last_run_ts: number;
  by_type: ERTypeMetrics[];
}

const BACKEND_LABEL: Record<string, string> = {
  splink: 'Splink',
  deterministic: 'детерминированный',
  deterministic_fallback: 'детерминированный (fallback)',
  trivial: 'нет пар',
  error: 'ошибка',
  unknown: '—',
};

function fmtTs(ts: number): string {
  if (!ts) return '—';
  try {
    return new Date(ts * 1000).toLocaleString('ru-RU');
  } catch {
    return String(ts);
  }
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof GitMerge;
  label: string;
  value: number | string;
  tone: string;
}) {
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-faint">
        <Icon size={15} className={tone} />
        {label}
      </div>
      <div className="mt-2 font-display text-3xl font-semibold text-ink">{value}</div>
    </div>
  );
}

export function ERMetricsView() {
  const q = useQuery({
    queryKey: ['er-metrics'],
    queryFn: () => apiGet<ERMetricsResponse>('/api/v1/admin/er-metrics'),
  });

  const m = q.data;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">ER observability · §8.13</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Метрики разрешения сущностей</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Наблюдаемость качества entity-resolution: живой прогон ER-пайплайна
          (<code>kg_er.resolve</code>) над каноническими узлами графа для каждого поддерживаемого
          типа сущностей. Счётчики решений движка — auto_merge / review_needed / separate —
          и число заблокированных перезаписей защищённых (reviewed) канониклов (§8.9). Те же
          значения отдаются в Prometheus-формате через{' '}
          <a
            href="/api/v1/admin/er-metrics?format=prometheus"
            target="_blank"
            rel="noreferrer"
            className="text-copper underline-offset-2 hover:underline"
          >
            ?format=prometheus
          </a>
          .
        </p>

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => q.refetch()}
            disabled={q.isFetching}
            className="btn-copper flex items-center gap-2"
          >
            {q.isFetching ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            {q.isFetching ? 'Пересчёт…' : 'Пересчитать метрики'}
          </button>
          {m && (
            <span className="text-xs text-faint">
              модель <span className="font-mono text-ink">{m.er_model_version}</span> · seed{' '}
              {m.er_random_seed} · прогон {fmtTs(m.er_last_run_ts)}
            </span>
          )}
        </div>

        {q.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка загрузки метрик: {(q.error as Error).message}
          </div>
        )}

        {q.isLoading && (
          <div className="flex items-center gap-2 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Прогон ER-пайплайна…
          </div>
        )}

        {m && (
          <div className="space-y-6">
            {/* Aggregate counters */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <StatCard
                icon={Boxes}
                label="Кандидаты"
                value={m.er_candidates_total}
                tone="text-sky-400"
              />
              <StatCard
                icon={GitMerge}
                label="Auto-merge"
                value={m.er_auto_merge_total}
                tone="text-emerald-400"
              />
              <StatCard
                icon={ShieldCheck}
                label="На ревью"
                value={m.er_review_needed_total}
                tone="text-amber-400"
              />
              <StatCard
                icon={SplitSquareHorizontal}
                label="Раздельно"
                value={m.er_separate_total}
                tone="text-faint"
              />
              <StatCard
                icon={Lock}
                label="Блок. перезаписи"
                value={m.er_blocked_overwrite_total}
                tone="text-red-400"
              />
            </div>

            {/* Per-type breakdown */}
            <div>
              <h3 className="mb-2 font-display text-lg">Разбивка по типам сущностей</h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Тип</th>
                      <th className="px-3 py-2 text-right">Узлов</th>
                      <th className="px-3 py-2 text-right">Кандидаты</th>
                      <th className="px-3 py-2 text-right">Auto-merge</th>
                      <th className="px-3 py-2 text-right">На ревью</th>
                      <th className="px-3 py-2 text-right">Раздельно</th>
                      <th className="px-3 py-2 text-right">Блок.</th>
                      <th className="px-3 py-2">Backend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.by_type.map((t) => (
                      <tr key={t.entity_type} className="border-b border-line/30">
                        <td className="px-3 py-2 text-ink">{t.entity_type}</td>
                        <td className="px-3 py-2 text-right font-mono text-faint">{t.n_input}</td>
                        <td className="px-3 py-2 text-right font-mono text-ink">
                          {t.candidates_total}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-emerald-400">
                          {t.auto_merge_total}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-amber-400">
                          {t.review_needed_total}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {t.separate_total}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-red-400">
                          {t.blocked_overwrite_total}
                        </td>
                        <td className="px-3 py-2 text-xs text-faint">
                          {BACKEND_LABEL[t.backend] ?? t.backend}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {m.er_candidates_total === 0 && (
              <div className="panel flex items-center gap-3 p-4 text-sm text-faint">
                <CircleCheck size={20} className="text-emerald-400" />
                Пока нет ER-кандидатов на слияние — либо в графе меньше двух узлов на тип, либо
                пайплайн не нашёл близких пар. После ingestion-прогона счётчики станут ненулевыми.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
