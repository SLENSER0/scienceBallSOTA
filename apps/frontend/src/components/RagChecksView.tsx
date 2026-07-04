import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  BadgeCheck,
  CircleCheck,
  CircleSlash,
  FlaskConical,
  Gauge,
  Loader2,
  Play,
  ShieldCheck,
} from 'lucide-react';

// §18.9 RAGAS + DeepEval RAG-checks UI. Self-contained (no api.ts edits): calls the
// rag-checks router directly with the same session-auth convention as api.ts.

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

interface Info {
  judge_model: string;
  ragas_metrics: string[];
  deepeval_metrics: string[];
  thresholds: Record<string, number>;
  higher_is_worse: string[];
  golden_size: number;
  note: string;
}

interface SampleReport {
  question: string;
  ragas: Record<string, number>;
  deepeval: Record<string, number>;
  citation_groundedness: number;
  hallucination: number;
  phantom_citations: string[];
  unsupported_claims: string[];
  thresholds: Record<string, number>;
  failures: string[];
  passed: boolean;
}

interface EvaluateResponse {
  report: SampleReport;
  ragas_row: { question: string; answer: string; contexts: string[]; ground_truth: string };
  deepeval_test_case: Record<string, unknown>;
  answer_markdown: string;
  n_contexts: number;
  n_citations: number;
}

interface AggregateResponse {
  n: number;
  ragas: Record<string, number>;
  deepeval: Record<string, number>;
  n_passed: number;
  n_phantom: number;
  judge_model: string;
  thresholds: Record<string, number>;
  failures: string[];
  passed: boolean;
  golden_size: number;
  per_sample: SampleReport[];
  mlflow_run: { run_id: string; experiment: string; tags: Record<string, string> } | null;
}

const METRIC_LABEL: Record<string, string> = {
  faithfulness: 'Faithfulness',
  answer_relevancy: 'Answer relevancy',
  context_precision: 'Context precision',
  contextual_precision: 'Context precision',
  context_recall: 'Context recall',
  answer_correctness: 'Answer correctness',
  citation_groundedness: 'Citation groundedness',
  hallucination: 'Hallucination ↓',
};

function fmt(v: number): string {
  return v.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
}

function MetricBar({
  name,
  value,
  threshold,
  worseIsHigher,
}: {
  name: string;
  value: number;
  threshold: number;
  worseIsHigher: boolean;
}) {
  const pass = worseIsHigher ? value <= threshold : value >= threshold;
  const width = Math.max(2, Math.min(100, value * 100));
  return (
    <div className="flex items-center gap-2 text-sm">
      <div className="w-44 shrink-0 text-ink">{METRIC_LABEL[name] ?? name}</div>
      <div className="relative h-3 flex-1 rounded bg-void/40">
        <div
          className={`h-3 rounded ${pass ? 'bg-emerald-500/70' : 'bg-red-500/70'}`}
          style={{ width: `${width}%` }}
        />
        <div
          className="absolute top-[-2px] h-4 w-[2px] bg-copper"
          style={{ left: `${Math.min(100, threshold * 100)}%` }}
          title={`порог ${fmt(threshold)}`}
        />
      </div>
      <div className={`w-14 text-right font-mono text-xs ${pass ? 'text-emerald-400' : 'text-red-400'}`}>
        {fmt(value)}
      </div>
      {pass ? (
        <CircleCheck size={14} className="text-emerald-400" />
      ) : (
        <CircleSlash size={14} className="text-red-400" />
      )}
    </div>
  );
}

function GateBanner({ passed, phantom, text }: { passed: boolean; phantom: number; text: string }) {
  return (
    <div
      className={`panel flex items-center gap-3 p-4 ${
        passed ? 'border-emerald-500/40' : 'border-red-500/40'
      }`}
    >
      {passed ? (
        <ShieldCheck size={28} className="text-emerald-400" />
      ) : (
        <CircleSlash size={28} className="text-red-400" />
      )}
      <div>
        <div className="font-display text-lg text-ink">
          {passed ? 'Gate пройден — галлюцинаций не найдено' : 'Gate не пройден'}
        </div>
        <div className="text-sm text-faint">
          {text}
          {phantom > 0 && (
            <span className="ml-1 text-red-400">· фантомных цитат: {phantom} (hard fail)</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function RagChecksView() {
  const [query, setQuery] = useState('');
  const [groundTruth, setGroundTruth] = useState('');
  const [single, setSingle] = useState<EvaluateResponse | null>(null);
  const [agg, setAgg] = useState<AggregateResponse | null>(null);

  const info = useQuery({ queryKey: ['rag-checks-info'], queryFn: () => apiGet<Info>('/api/v1/rag-checks/info') });

  const evaluate = useMutation({
    mutationFn: () =>
      apiPost<EvaluateResponse>('/api/v1/rag-checks/evaluate', {
        query,
        ground_truth: groundTruth,
      }),
    onSuccess: (d) => setSingle(d),
  });

  const run = useMutation({
    mutationFn: () => apiPost<AggregateResponse>('/api/v1/rag-checks/run', { use_llm: false, log_mlflow: true }),
    onSuccess: (d) => setAgg(d),
  });

  const thr = info.data?.thresholds ?? {};
  const worse = new Set(info.data?.higher_is_worse ?? []);
  const metricRow = (metrics: Record<string, number>) =>
    Object.entries(metrics).map(([name, value]) => (
      <MetricBar
        key={name}
        name={name}
        value={value}
        threshold={thr[name] ?? (worse.has(name) ? 0.1 : 0.5)}
        worseIsHigher={worse.has(name)}
      />
    ));

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">faithfulness / hallucination · §18.9</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">RAGAS + DeepEval RAG-checks</h2>
        <p className="mb-4 max-w-3xl text-sm text-faint">
          Измеримое доказательство «нет галлюцинаций» отраслевыми метриками: пять RAGAS-метрик
          (faithfulness, answer relevancy, context precision/recall, answer correctness) и DeepEval-набор
          (Faithfulness / AnswerRelevancy / ContextualPrecision / Hallucination) плюс кастомная
          GEval-метрика «citation groundedness» под evidence-first модель. Каждая численная claim обязана
          опираться на резолвимую цитату; фантомная ссылка — hard fail.
        </p>

        {info.data && (
          <div className="panel mb-5 flex flex-wrap items-center gap-x-6 gap-y-1 p-3 text-xs text-faint">
            <span className="flex items-center gap-1">
              <Gauge size={13} className="text-copper" /> Judge:{' '}
              <span className="font-mono text-ink">{info.data.judge_model}</span>
            </span>
            <span>Golden-набор: {info.data.golden_size} вопросов</span>
            <span className="text-faint/80">{info.data.note}</span>
          </div>
        )}

        {/* ── Ad-hoc single-query evaluation ── */}
        <div className="panel mb-6 space-y-3 p-4">
          <div className="flex items-center gap-2 font-display text-lg text-ink">
            <BadgeCheck size={18} className="text-copper" /> Проверить один ответ
          </div>
          <input
            className="w-full rounded border border-line/60 bg-void/30 px-3 py-2 text-sm text-ink outline-none focus:border-copper"
            placeholder="Вопрос к агенту (например: удельная производительность обратного осмоса)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <input
            className="w-full rounded border border-line/60 bg-void/30 px-3 py-2 text-sm text-ink outline-none focus:border-copper"
            placeholder="Ground truth (опц.) — эталонный ответ для answer_correctness / context_recall"
            value={groundTruth}
            onChange={(e) => setGroundTruth(e.target.value)}
          />
          <button
            onClick={() => evaluate.mutate()}
            disabled={evaluate.isPending || !query.trim()}
            className="btn-copper flex items-center gap-2"
          >
            {evaluate.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {evaluate.isPending ? 'Оценка ответа…' : 'Оценить'}
          </button>
          {evaluate.isError && (
            <div className="text-sm text-red-400">Ошибка: {(evaluate.error as Error).message}</div>
          )}

          {single && (
            <div className="space-y-4 pt-2">
              <GateBanner
                passed={single.report.passed}
                phantom={single.report.phantom_citations.length}
                text={`${single.n_citations} цитат · ${single.n_contexts} контекстов${
                  single.report.failures.length
                    ? ` · провалы: ${single.report.failures.join(', ')}`
                    : ''
                }`}
              />
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <div className="mb-2 text-xs uppercase text-faint">RAGAS</div>
                  <div className="space-y-2">{metricRow(single.report.ragas)}</div>
                </div>
                <div>
                  <div className="mb-2 text-xs uppercase text-faint">DeepEval</div>
                  <div className="space-y-2">{metricRow(single.report.deepeval)}</div>
                </div>
              </div>
              {single.report.unsupported_claims.length > 0 && (
                <div className="panel border-amber-500/40 p-3">
                  <div className="mb-1 text-xs uppercase text-amber-400">
                    Неподтверждённые claims ({single.report.unsupported_claims.length})
                  </div>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-faint">
                    {single.report.unsupported_claims.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
              <details className="text-xs text-faint">
                <summary className="cursor-pointer">Ответ агента (markdown)</summary>
                <pre className="mt-2 whitespace-pre-wrap rounded bg-void/30 p-3 text-ink">
                  {single.answer_markdown}
                </pre>
              </details>
            </div>
          )}
        </div>

        {/* ── Golden suite run ── */}
        <div className="panel space-y-3 p-4">
          <div className="flex items-center gap-2 font-display text-lg text-ink">
            <FlaskConical size={18} className="text-copper" /> Прогон golden-набора (suite ragas)
          </div>
          <p className="text-sm text-faint">
            Прогоняет весь golden-набор через живого агента, агрегирует RAGAS/DeepEval-метрики с порогами
            как gate и логирует их в MLflow-эксперимент <span className="font-mono">answer</span> с
            зафиксированной judge-моделью в тегах (воспроизводимость).
          </p>
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="btn-copper flex items-center gap-2"
          >
            {run.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {run.isPending ? 'Прогон…' : 'Запустить suite'}
          </button>
          {run.isError && <div className="text-sm text-red-400">Ошибка: {(run.error as Error).message}</div>}

          {agg && (
            <div className="space-y-4 pt-2">
              <GateBanner
                passed={agg.passed}
                phantom={agg.n_phantom}
                text={`${agg.n_passed}/${agg.n} вопросов прошли · ${agg.n} в наборе${
                  agg.failures.length ? ` · провалы среднего: ${agg.failures.join(', ')}` : ''
                }`}
              />
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <div className="mb-2 text-xs uppercase text-faint">RAGAS (среднее)</div>
                  <div className="space-y-2">{metricRow(agg.ragas)}</div>
                </div>
                <div>
                  <div className="mb-2 text-xs uppercase text-faint">DeepEval (среднее)</div>
                  <div className="space-y-2">{metricRow(agg.deepeval)}</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Вопрос</th>
                      <th className="px-3 py-2 text-right">Faith.</th>
                      <th className="px-3 py-2 text-right">Halluc.↓</th>
                      <th className="px-3 py-2 text-right">Cite-ground.</th>
                      <th className="px-3 py-2 text-center">Gate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agg.per_sample.map((r, i) => (
                      <tr key={i} className="border-b border-line/30">
                        <td className="px-3 py-2 text-ink">{r.question}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(r.ragas.faithfulness)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(r.hallucination)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmt(r.citation_groundedness)}</td>
                        <td className="px-3 py-2 text-center">
                          {r.passed ? (
                            <CircleCheck size={15} className="mx-auto text-emerald-400" />
                          ) : (
                            <CircleSlash size={15} className="mx-auto text-red-400" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {agg.mlflow_run && (
                <div className="text-xs text-faint">
                  MLflow · experiment <span className="font-mono text-ink">{agg.mlflow_run.experiment}</span>{' '}
                  · run <span className="font-mono text-ink">{agg.mlflow_run.run_id}</span> · judge{' '}
                  <span className="font-mono text-ink">{agg.judge_model}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
