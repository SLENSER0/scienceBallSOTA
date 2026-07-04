import { useQuery } from '@tanstack/react-query';
import {
  CircleCheck,
  CircleSlash,
  Coins,
  FileText,
  Gauge,
  Loader2,
  Ruler,
  Target,
  Timer,
} from 'lucide-react';

// §6.17 extraction eval-dashboard. Self-contained (no api.ts edits): calls the
// extraction-eval router directly with the same session-auth convention as api.ts.

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

interface TypeScore {
  entity_type: string;
  support: number;
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
}
interface AcceptanceEntry {
  value: number;
  threshold: number;
  pass: boolean;
}
interface PerDoc {
  doc_id: string;
  title: string;
  n_gold: number;
  n_pred: number;
  n_matched: number;
  useful: boolean;
  latency_ms: number;
  cost_usd: number;
}
interface EvalReport {
  pipeline_version: string;
  n_docs: number;
  n_gold: number;
  n_pred: number;
  n_matched: number;
  by_type: TypeScore[];
  micro_precision: number;
  micro_recall: number;
  micro_f1: number;
  macro_f1: number;
  span_mean_iou: number;
  span_accuracy: number;
  measurement_value_accuracy: number;
  measurement_unit_accuracy: number;
  evidence_span_ratio: number;
  useful_docs_rate: number;
  cost_per_doc_usd: number;
  total_cost_usd: number;
  latency_ms_per_doc: number;
  total_latency_ms: number;
  tokens_per_doc: number;
  per_doc: PerDoc[];
  acceptance: Record<string, AcceptanceEntry | boolean>;
  thresholds: { iou_match: number; iou_strict: number };
}

const TYPE_LABEL: Record<string, string> = {
  material: 'Материалы',
  process: 'Обработка',
  measurement: 'Измерения',
};
const ACCEPT_LABEL: Record<string, string> = {
  useful_docs_rate: 'Полезные граф-факты (доля документов)',
  span_accuracy: 'Span-accuracy (IoU ≥ 0.9)',
  measurement_evidence: 'Измерения с валидным Evidence',
};

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}
function fmt(v: number, dp = 4): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(dp).replace(/0+$/, '').replace(/\.$/, '');
}

function Stat({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="panel p-3">
      <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wide text-faint">
        {icon}
        {label}
      </div>
      <div className="font-display text-2xl text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-faint">{sub}</div>}
    </div>
  );
}

function Bar({ value, tone }: { value: number; tone: string }) {
  return (
    <div className="h-2 w-full rounded bg-void/40">
      <div className={`h-2 rounded ${tone}`} style={{ width: `${Math.min(100, value * 100)}%` }} />
    </div>
  );
}

export function ExtractionEvalView() {
  const report = useQuery({
    queryKey: ['extraction-eval-report'],
    queryFn: () => apiGet<EvalReport>('/api/v1/extraction-eval/report'),
  });

  const d = report.data;
  const overallPass = d ? d.acceptance.overall_pass === true : false;
  const acceptEntries = d
    ? Object.entries(d.acceptance).filter(
        (e): e is [string, AcceptanceEntry] => typeof e[1] === 'object',
      )
    : [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">extraction quality · §6.17</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Extraction eval-дашборд</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Доказуемое качество извлечения на «золотом» наборе: precision / recall / F1 по типам
          сущностей (материалы · обработка · измерения), точность спанов по IoU символьных офсетов,
          (value, unit) accuracy для измерений, доля фактов с валидным Evidence и cost / latency на
          документ. Детерминированный референс-экстрактор (rule-слой, без LLM) — воспроизводимая
          нижняя граница качества.
        </p>

        {report.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Прогон eval на golden-наборе…
          </div>
        )}
        {report.isError && (
          <div className="panel border-red-500/40 p-3 text-sm text-red-400">
            Ошибка: {(report.error as Error).message}
          </div>
        )}

        {d && (
          <div className="space-y-6">
            {/* Acceptance banner */}
            <div
              className={`panel flex flex-wrap items-center gap-4 p-4 ${
                overallPass ? 'border-emerald-500/40' : 'border-amber-500/40'
              }`}
            >
              {overallPass ? (
                <CircleCheck size={28} className="text-emerald-400" />
              ) : (
                <CircleSlash size={28} className="text-amber-400" />
              )}
              <div className="flex-1">
                <div className="font-display text-lg text-ink">
                  {overallPass ? 'Критерий приёмки §6.17 выполнен' : 'Критерий приёмки §6.17 не выполнен'}
                </div>
                <div className="text-sm text-faint">
                  {d.n_docs} документов · {d.n_gold} gold-сущностей · {d.n_matched} сматчено ·
                  pipeline <span className="font-mono text-xs">{d.pipeline_version}</span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {acceptEntries.map(([key, v]) => (
                  <div
                    key={key}
                    className={`rounded px-2 py-1 text-xs ${
                      v.pass
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-amber-500/10 text-amber-400'
                    }`}
                    title={`${ACCEPT_LABEL[key] ?? key} ≥ ${v.threshold}`}
                  >
                    {ACCEPT_LABEL[key] ?? key}: {fmt(v.value)}
                    {v.pass ? ' ✓' : ' ✗'}
                  </div>
                ))}
              </div>
            </div>

            {/* Headline stats */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                icon={<Gauge size={13} />}
                label="Micro F1"
                value={fmt(d.micro_f1)}
                sub={`P ${fmt(d.micro_precision)} · R ${fmt(d.micro_recall)} · macro ${fmt(d.macro_f1)}`}
              />
              <Stat
                icon={<Ruler size={13} />}
                label="Span-accuracy (IoU≥0.9)"
                value={pct(d.span_accuracy)}
                sub={`mean IoU ${fmt(d.span_mean_iou)} · match@${d.thresholds.iou_match}`}
              />
              <Stat
                icon={<Target size={13} />}
                label="Measurement value/unit"
                value={`${pct(d.measurement_value_accuracy)} / ${pct(d.measurement_unit_accuracy)}`}
                sub={`evidence-span ${pct(d.evidence_span_ratio)}`}
              />
              <Stat
                icon={<Timer size={13} />}
                label="Latency / документ"
                value={`${fmt(d.latency_ms_per_doc, 3)} ms`}
                sub={`≈ ${fmt(d.tokens_per_doc, 1)} токенов · $${fmt(d.cost_per_doc_usd, 6)}/док`}
              />
            </div>

            {/* Per-type P/R/F1 */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Gauge size={18} className="text-copper" /> Precision / Recall / F1 по типам
              </h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Тип</th>
                      <th className="px-3 py-2 text-right">Gold</th>
                      <th className="px-3 py-2 text-right">TP</th>
                      <th className="px-3 py-2 text-right">FP</th>
                      <th className="px-3 py-2 text-right">FN</th>
                      <th className="px-3 py-2 text-right">Precision</th>
                      <th className="px-3 py-2 text-right">Recall</th>
                      <th className="px-3 py-2 text-right">F1</th>
                      <th className="px-3 py-2 w-40">F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.by_type.map((t) => (
                      <tr key={t.entity_type} className="border-b border-line/30">
                        <td className="px-3 py-2 text-ink">
                          {TYPE_LABEL[t.entity_type] ?? t.entity_type}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">{t.support}</td>
                        <td className="px-3 py-2 text-right font-mono text-emerald-400">{t.tp}</td>
                        <td className="px-3 py-2 text-right font-mono text-amber-400">{t.fp}</td>
                        <td className="px-3 py-2 text-right font-mono text-red-400">{t.fn}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(t.precision)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(t.recall)}</td>
                        <td className="px-3 py-2 text-right font-mono font-bold text-ink">
                          {fmt(t.f1)}
                        </td>
                        <td className="px-3 py-2">
                          <Bar value={t.f1} tone="bg-copper" />
                        </td>
                      </tr>
                    ))}
                    <tr className="text-xs text-faint">
                      <td className="px-3 py-2 font-medium text-ink">micro</td>
                      <td className="px-3 py-2 text-right font-mono">{d.n_gold}</td>
                      <td colSpan={2} />
                      <td />
                      <td className="px-3 py-2 text-right font-mono">{fmt(d.micro_precision)}</td>
                      <td className="px-3 py-2 text-right font-mono">{fmt(d.micro_recall)}</td>
                      <td className="px-3 py-2 text-right font-mono font-bold text-ink">
                        {fmt(d.micro_f1)}
                      </td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Per-document breakdown with cost/latency */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <FileText size={18} className="text-copper" /> Golden-документы ({d.n_docs}) —
                cost/latency
                <span className="ml-2 text-xs font-normal text-faint">
                  <Coins size={12} className="mr-1 inline" />
                  всего ${fmt(d.total_cost_usd, 6)} · {fmt(d.total_latency_ms, 3)} ms
                </span>
              </h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Документ</th>
                      <th className="px-3 py-2 text-right">Gold</th>
                      <th className="px-3 py-2 text-right">Pred</th>
                      <th className="px-3 py-2 text-right">Match</th>
                      <th className="px-3 py-2 text-right">Latency</th>
                      <th className="px-3 py-2 text-right">Cost</th>
                      <th className="px-3 py-2 text-center">Полезный</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.per_doc.map((doc) => (
                      <tr key={doc.doc_id} className="border-b border-line/30">
                        <td className="px-3 py-2 text-ink" title={doc.doc_id}>
                          {doc.title}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">{doc.n_gold}</td>
                        <td className="px-3 py-2 text-right font-mono text-faint">{doc.n_pred}</td>
                        <td className="px-3 py-2 text-right font-mono text-emerald-400">
                          {doc.n_matched}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {fmt(doc.latency_ms, 3)} ms
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          ${fmt(doc.cost_usd, 6)}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {doc.useful ? (
                            <CircleCheck size={15} className="mx-auto text-emerald-400" />
                          ) : (
                            <CircleSlash size={15} className="mx-auto text-amber-400" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 text-[10px] text-faint">
                Cost — оценка по референс-тарифу (§18.10); референс-экстрактор LLM не вызывает.
                Latency — реальный wall-clock прогона слоя над фрагментом.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
