import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  DollarSign,
  Gauge,
  Loader2,
  RefreshCw,
} from 'lucide-react';

// §18.5 Ops-дашборды (latency p95 · throughput · LLM-cost · curation) + алерты.
// Self-contained (без правок api.ts): бьёт в роутер /api/v1/ops-dashboards напрямую
// той же session-auth-конвенцией, что и api.ts; авто-refresh каждые 10с (live-дашборд).

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

interface LatencyRoute {
  route: string;
  count: number;
  errors: number;
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  slo_breach: boolean;
}
interface LatencyDash {
  slo_p95_ms: number;
  overall: { p50_ms: number; p95_ms: number; p99_ms: number; sampled_requests: number };
  slo_breaches: number;
  routes: LatencyRoute[];
}
interface ThroughputRoute {
  route: string;
  count: number;
  errors: number;
  error_rate: number;
  rps: number;
}
interface ThroughputDash {
  uptime_s: number;
  total_requests: number;
  total_errors: number;
  error_rate: number;
  throughput_rps: number;
  routes: ThroughputRoute[];
}
interface CostDoc {
  document_id: string;
  name: string;
  prompt_tokens: number;
  cost_usd: number;
}
interface CostDash {
  model_id: string;
  price_usd_per_1k: { input: number; output: number };
  estimate_note: string;
  extraction: {
    documents_sampled: number;
    total_prompt_tokens: number;
    total_cost_usd: number;
    extraction_cost_usd_per_document: number;
    top_documents: CostDoc[];
  };
  answer: { answer_cost_usd_per_query: number; prompt_tokens: number; completion_tokens: number };
}
interface CurationEvent {
  action: string;
  actor: string;
  created_at: string;
  target: string;
}
interface CurationDash {
  total_events: number;
  corrections: number;
  extractions: number;
  reviewer_corrections_per_100_extractions: number;
  by_action: Record<string, number>;
  by_actor: Record<string, number>;
  recent: CurationEvent[];
}
interface AlertRule {
  id: string;
  title: string;
  severity: string;
  value: number;
  threshold: number;
  firing: boolean;
  detail: string;
}
interface AlertsDash {
  firing_count: number;
  status: string;
  rules: AlertRule[];
}
interface Overview {
  latency: LatencyDash;
  throughput: ThroughputDash;
  cost: CostDash;
  curation: CurationDash;
  alerts: AlertsDash;
}

function fmtUsd(v: number): string {
  if (v === 0) return '$0';
  if (v < 0.01) return `$${v.toFixed(6)}`;
  return `$${v.toFixed(4)}`;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="panel p-3">
      <div className="text-xs uppercase tracking-wide text-faint">{label}</div>
      <div className="mt-1 font-display text-2xl font-semibold text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-faint">{hint}</div>}
    </div>
  );
}

export function OpsDashboardsView() {
  const q = useQuery({
    queryKey: ['ops-dashboards-overview'],
    queryFn: () => apiGet<Overview>('/api/v1/ops-dashboards/overview'),
    refetchInterval: 10_000,
  });

  const d = q.data;
  const alerts = d?.alerts;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">observability · §18.5</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Ops-дашборды и алерты</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Четыре живых дашборда наблюдаемости — latency p50/p95/p99, throughput/error-rate,
          LLM-cost (extraction/doc · answer/query) и curation (reviewer-corrections) — плюс контур
          алертов. Headline-правило: алерт при <b>unsupported-claim-rate&nbsp;&gt;&nbsp;0</b>{' '}
          (guardrail «нет числа без evidence», §16). Авто-обновление каждые 10&nbsp;с.
        </p>

        <div className="mb-5 flex items-center gap-3">
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
            Обновить
          </button>
          {d && (
            <span className="text-xs text-faint">
              uptime {d.throughput.uptime_s}s · {d.throughput.total_requests} запросов
            </span>
          )}
        </div>

        {q.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка загрузки: {(q.error as Error).message}
          </div>
        )}

        {!d && !q.isError && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка метрик…
          </div>
        )}

        {d && (
          <div className="space-y-6">
            {/* Alerts banner */}
            <div
              className={`panel flex items-start gap-3 p-4 ${
                alerts && alerts.firing_count > 0 ? 'border-red-500/50' : 'border-emerald-500/40'
              }`}
            >
              {alerts && alerts.firing_count > 0 ? (
                <AlertTriangle size={26} className="mt-0.5 shrink-0 text-red-400" />
              ) : (
                <CheckCircle2 size={26} className="mt-0.5 shrink-0 text-emerald-400" />
              )}
              <div className="min-w-0 flex-1">
                <div className="font-display text-lg text-ink">
                  {alerts && alerts.firing_count > 0
                    ? `${alerts.firing_count} алерт(ов) активно`
                    : 'Все правила в норме'}
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {alerts?.rules.map((r) => (
                    <div
                      key={r.id}
                      className={`flex items-center justify-between gap-2 rounded border px-3 py-2 text-sm ${
                        r.firing
                          ? r.severity === 'critical'
                            ? 'border-red-500/50 text-red-300'
                            : 'border-amber-500/50 text-amber-300'
                          : 'border-white/10 text-faint'
                      }`}
                    >
                      <span className="truncate">{r.title}</span>
                      <span className="shrink-0 font-mono text-xs">
                        {r.firing ? '● ' : '○ '}
                        {r.value}
                        {r.threshold ? ` / ${r.threshold}` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Latency dashboard */}
            <section>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Gauge size={18} className="text-copper" /> Latency (p50 / p95 / p99)
              </h3>
              <div className="mb-3 grid gap-3 sm:grid-cols-4">
                <Stat label="overall p50" value={`${d.latency.overall.p50_ms} ms`} />
                <Stat
                  label="overall p95"
                  value={`${d.latency.overall.p95_ms} ms`}
                  hint={`SLO ${d.latency.slo_p95_ms} ms`}
                />
                <Stat label="overall p99" value={`${d.latency.overall.p99_ms} ms`} />
                <Stat
                  label="SLO breaches"
                  value={String(d.latency.slo_breaches)}
                  hint={`${d.latency.overall.sampled_requests} sampled`}
                />
              </div>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-xs text-faint">
                      <th className="px-3 py-2">route</th>
                      <th className="px-3 py-2 text-right">count</th>
                      <th className="px-3 py-2 text-right">p50</th>
                      <th className="px-3 py-2 text-right">p95</th>
                      <th className="px-3 py-2 text-right">p99</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.latency.routes.map((r) => (
                      <tr key={r.route} className="border-b border-white/5">
                        <td className="px-3 py-1.5 font-mono text-xs text-ink">{r.route}</td>
                        <td className="px-3 py-1.5 text-right text-faint">{r.count}</td>
                        <td className="px-3 py-1.5 text-right">{r.p50_ms}</td>
                        <td
                          className={`px-3 py-1.5 text-right ${r.slo_breach ? 'text-red-400' : ''}`}
                        >
                          {r.p95_ms}
                        </td>
                        <td className="px-3 py-1.5 text-right text-faint">{r.p99_ms}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Throughput dashboard */}
            <section>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Activity size={18} className="text-copper" /> Throughput
              </h3>
              <div className="grid gap-3 sm:grid-cols-4">
                <Stat label="total requests" value={String(d.throughput.total_requests)} />
                <Stat label="throughput" value={`${d.throughput.throughput_rps} rps`} />
                <Stat
                  label="error rate"
                  value={`${(d.throughput.error_rate * 100).toFixed(2)}%`}
                  hint={`${d.throughput.total_errors} errors`}
                />
                <Stat label="uptime" value={`${d.throughput.uptime_s}s`} />
              </div>
            </section>

            {/* Cost dashboard */}
            <section>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <DollarSign size={18} className="text-copper" /> LLM cost
              </h3>
              <div className="mb-2 grid gap-3 sm:grid-cols-3">
                <Stat
                  label="cost / document"
                  value={fmtUsd(d.cost.extraction.extraction_cost_usd_per_document)}
                  hint={`${d.cost.extraction.documents_sampled} docs`}
                />
                <Stat
                  label="cost / query"
                  value={fmtUsd(d.cost.answer.answer_cost_usd_per_query)}
                  hint={`${d.cost.answer.prompt_tokens}+${d.cost.answer.completion_tokens} tok`}
                />
                <Stat
                  label="model"
                  value={d.cost.model_id}
                  hint={`in ${d.cost.price_usd_per_1k.input} / out ${d.cost.price_usd_per_1k.output} $/1k`}
                />
              </div>
              <p className="mb-2 text-xs text-faint">{d.cost.estimate_note}</p>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-xs text-faint">
                      <th className="px-3 py-2">document</th>
                      <th className="px-3 py-2 text-right">tokens</th>
                      <th className="px-3 py-2 text-right">cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.cost.extraction.top_documents.map((doc) => (
                      <tr key={doc.document_id} className="border-b border-white/5">
                        <td className="px-3 py-1.5 text-xs text-ink">{doc.name}</td>
                        <td className="px-3 py-1.5 text-right text-faint">{doc.prompt_tokens}</td>
                        <td className="px-3 py-1.5 text-right">{fmtUsd(doc.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Curation dashboard */}
            <section>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <ClipboardCheck size={18} className="text-copper" /> Curation
              </h3>
              <div className="mb-3 grid gap-3 sm:grid-cols-4">
                <Stat
                  label="corrections / 100 extr."
                  value={String(d.curation.reviewer_corrections_per_100_extractions)}
                />
                <Stat label="total events" value={String(d.curation.total_events)} />
                <Stat label="corrections" value={String(d.curation.corrections)} />
                <Stat label="extractions" value={String(d.curation.extractions)} />
              </div>
              {Object.keys(d.curation.by_action).length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {Object.entries(d.curation.by_action).map(([action, n]) => (
                    <span
                      key={action}
                      className="rounded border border-white/10 px-2 py-1 text-xs text-nickel"
                    >
                      {action}: <b className="text-ink">{n}</b>
                    </span>
                  ))}
                </div>
              )}
              {d.curation.recent.length > 0 && (
                <div className="panel overflow-x-auto p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-left text-xs text-faint">
                        <th className="px-3 py-2">action</th>
                        <th className="px-3 py-2">actor</th>
                        <th className="px-3 py-2">target</th>
                        <th className="px-3 py-2">at</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.curation.recent.map((e, i) => (
                        <tr key={i} className="border-b border-white/5">
                          <td className="px-3 py-1.5 font-mono text-xs text-copper">{e.action}</td>
                          <td className="px-3 py-1.5 text-xs text-ink">{e.actor}</td>
                          <td className="px-3 py-1.5 text-xs text-faint">{e.target}</td>
                          <td className="px-3 py-1.5 text-xs text-faint">{e.created_at}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {d.curation.total_events === 0 && (
                <div className="panel p-3 text-sm text-faint">
                  Пока нет curation-событий — правки кураторов появятся здесь.
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
