import { useQuery } from '@tanstack/react-query';
import { CircleCheck, CircleSlash, Loader2, ShieldCheck, Target } from 'lucide-react';

// §8.12 Golden ER-set F1 + CI regression gate. Self-contained (no api.ts edits):
// calls the er_eval router directly with the same session-auth convention as api.ts.

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

interface PRF {
  precision: number;
  recall: number;
  f1: number;
}
interface TypeEval {
  entity_type: string;
  file: string;
  threshold: number;
  f1: number;
  passed: boolean;
  n_mentions: number;
  n_gold_clusters: number;
  n_predicted_clusters: number;
  backend: string;
  pairwise: PRF;
  b_cubed: PRF;
  purity: number;
  inverse_purity: number;
}
interface EvalReport {
  passed: boolean;
  min_f1: number;
  mean_f1: number;
  n_types: number;
  types: TypeEval[];
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const f3 = (v: number) => v.toFixed(3);

const TYPE_LABEL: Record<string, string> = {
  Material: 'Материалы',
  Equipment: 'Оборудование',
  Person: 'Персоны',
  Lab: 'Лаборатории',
};

function F1Bar({ t }: { t: TypeEval }) {
  const barPct = Math.max(0, Math.min(100, t.f1 * 100));
  const thrPct = Math.max(0, Math.min(100, t.threshold * 100));
  const good = t.passed;
  return (
    <div className="panel p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <div className="font-display text-sm text-ink">
          {TYPE_LABEL[t.entity_type] ?? t.entity_type}
        </div>
        <div className={`font-mono text-lg font-semibold ${good ? 'text-emerald-400' : 'text-red-400'}`}>
          {f3(t.f1)}
        </div>
      </div>
      {/* F1 bar with threshold marker */}
      <div className="relative h-3 w-full overflow-hidden rounded bg-white/5">
        <div
          className={`h-full rounded ${good ? 'bg-emerald-500/70' : 'bg-red-500/70'}`}
          style={{ width: `${barPct}%` }}
        />
        <div
          className="absolute top-[-3px] h-[18px] w-[2px] bg-amber-400"
          style={{ left: `${thrPct}%` }}
          title={`порог ${f3(t.threshold)}`}
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-faint">
        <span>P {pct(t.pairwise.precision)}</span>
        <span>R {pct(t.pairwise.recall)}</span>
        <span>B³-F1 {f3(t.b_cubed.f1)}</span>
        <span>порог {f3(t.threshold)}</span>
        <span>
          {t.n_mentions} упоминаний · {t.n_gold_clusters} эталонных групп
        </span>
      </div>
    </div>
  );
}

export function ErEvalView() {
  const q = useQuery({
    queryKey: ['er-eval'],
    queryFn: () => apiGet<EvalReport>('/api/v1/er/eval'),
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">качество ER · §8.12</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Golden-набор ER · F1 и гейт регрессии</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Измеримое доказательство качества разрешения сущностей: реальный резолвер прогоняется по
          размеченному golden-набору (материалы / оборудование / персоны / лаборатории), а
          predicted-кластеры сравниваются с эталонными парами — pairwise precision/recall/F1 и
          cluster-метрики (B³, purity). Порог по каждому типу защищает CI от деградации моделей: если
          F1 падает ниже порога — гейт красный.
        </p>

        {q.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Прогон eval по golden-набору…
          </div>
        )}
        {q.isError && (
          <div className="panel border-red-500/40 p-3 text-sm text-red-400">
            Ошибка eval: {(q.error as Error).message}
          </div>
        )}

        {q.data && (
          <div className="space-y-5">
            {/* Gate banner */}
            <div
              className={`panel flex items-center gap-3 p-4 ${
                q.data.passed ? 'border-emerald-500/40' : 'border-red-500/40'
              }`}
            >
              {q.data.passed ? (
                <ShieldCheck size={28} className="text-emerald-400" />
              ) : (
                <CircleSlash size={28} className="text-red-400" />
              )}
              <div className="flex-1">
                <div className="font-display text-lg text-ink">
                  {q.data.passed ? 'Гейт регрессии: PASS' : 'Гейт регрессии: FAIL'}
                </div>
                <div className="text-sm text-faint">
                  Средний F1 {f3(q.data.mean_f1)} · минимальный F1 {f3(q.data.min_f1)} по{' '}
                  {q.data.n_types} типам. Все типы выше порога приёмки — качество ER подтверждено.
                </div>
              </div>
              <div className="text-right">
                <div className="flex items-center gap-1 text-2xl font-semibold text-ink">
                  <Target size={20} className="text-copper" />
                  {f3(q.data.mean_f1)}
                </div>
                <div className="text-xs text-faint">средний F1</div>
              </div>
            </div>

            {/* Per-type F1 bars */}
            <div className="grid gap-3 sm:grid-cols-2">
              {q.data.types.map((t) => (
                <F1Bar key={t.entity_type} t={t} />
              ))}
            </div>

            {/* Detail table */}
            <div className="panel overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="text-faint">
                  <tr className="border-b border-white/10 text-left">
                    <th className="px-3 py-2 font-medium">Тип</th>
                    <th className="px-3 py-2 font-medium">F1</th>
                    <th className="px-3 py-2 font-medium">Precision</th>
                    <th className="px-3 py-2 font-medium">Recall</th>
                    <th className="px-3 py-2 font-medium">B³-F1</th>
                    <th className="px-3 py-2 font-medium">Purity</th>
                    <th className="px-3 py-2 font-medium">Порог</th>
                    <th className="px-3 py-2 font-medium">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.types.map((t) => (
                    <tr key={t.entity_type} className="border-b border-white/5">
                      <td className="px-3 py-2 text-ink">
                        {TYPE_LABEL[t.entity_type] ?? t.entity_type}
                        <span className="ml-1 text-xs text-faint">({t.backend})</span>
                      </td>
                      <td className="px-3 py-2 font-mono">{f3(t.f1)}</td>
                      <td className="px-3 py-2 font-mono">{f3(t.pairwise.precision)}</td>
                      <td className="px-3 py-2 font-mono">{f3(t.pairwise.recall)}</td>
                      <td className="px-3 py-2 font-mono">{f3(t.b_cubed.f1)}</td>
                      <td className="px-3 py-2 font-mono">{f3(t.purity)}</td>
                      <td className="px-3 py-2 font-mono text-faint">{f3(t.threshold)}</td>
                      <td className="px-3 py-2">
                        {t.passed ? (
                          <span className="inline-flex items-center gap-1 text-emerald-400">
                            <CircleCheck size={14} /> PASS
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-red-400">
                            <CircleSlash size={14} /> FAIL
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-faint">
              Гейт также исполняется в CI как pytest —{' '}
              <span className="font-mono">packages/kg_er/tests/test_golden_eval.py</span>: падает,
              если pairwise-F1 любого типа опускается ниже порога из{' '}
              <span className="font-mono">er_eval_thresholds.yaml</span>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
