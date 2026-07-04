import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { GitFork, Lightbulb, Sparkles, TriangleAlert } from 'lucide-react';
import { api } from '../api';

// §13.11 Mode D — предсказание недостающих связей. «Граф думает»: по топологии
// реального графа предлагаем вероятные, но не проведённые связи material↔lab/…

const METRICS: { id: string; label: string }[] = [
  { id: 'adamic_adar', label: 'Adamic / Adar' },
  { id: 'resource_allocation', label: 'Resource allocation' },
  { id: 'jaccard', label: 'Jaccard' },
  { id: 'common', label: 'Общие соседи' },
  { id: 'preferential', label: 'Preferential attachment' },
];

const TARGETS: { id: string; label: string }[] = [
  { id: '', label: 'Любые узлы' },
  { id: 'Lab', label: 'Лаборатории' },
  { id: 'Property', label: 'Свойства' },
  { id: 'ProcessingRegime', label: 'Режимы' },
  { id: 'Equipment', label: 'Оборудование' },
  { id: 'Material', label: 'Материалы' },
];

export function LinkPredictionView() {
  const [seed, setSeed] = useState('');
  const [metric, setMetric] = useState('adamic_adar');
  const [target, setTarget] = useState('');

  const seeds = useQuery({ queryKey: ['lp-seeds'], queryFn: () => api.linkPredictionSeeds('Material') });
  const seedId = seed || seeds.data?.seeds[0]?.id || '';

  const pred = useQuery({
    queryKey: ['lp-predict', seedId, metric, target],
    queryFn: () => api.linkPredict(seedId, metric, target || undefined),
    enabled: !!seedId,
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">граф думает · Mode D · §13.11</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Предсказание недостающих связей</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          По топологии графа подбираем вероятные, но пока не проведённые связи — общие соседи,
          Adamic/Adar, Jaccard. Рёбра не создаются: это подсказка, какой эксперимент поставить.
        </p>

        <div className="mb-5 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Материал</span>
            <select
              value={seedId}
              onChange={(e) => setSeed(e.target.value)}
              className="min-w-64 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {seeds.data?.seeds.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name || s.id}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Метрика</span>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {METRICS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Тип узла</span>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {TARGETS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {pred.isLoading && <div className="text-sm text-faint">Граф считает близость…</div>}
        {pred.isError && (
          <div className="flex items-center gap-2 text-sm text-copper">
            <TriangleAlert size={15} /> Не удалось получить предсказания.
          </div>
        )}

        {pred.data && pred.data.count === 0 && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            Нет кандидатов с топологическим сигналом для выбранных фильтров.
          </div>
        )}

        {pred.data && pred.data.count > 0 && (
          <ul className="space-y-2">
            {pred.data.predictions.map((p) => (
              <li
                key={p.target}
                className="rounded-lg border border-line bg-surface/50 px-4 py-3 transition hover:border-copper/40"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <GitFork size={15} className="shrink-0 text-copper" />
                    <span className="truncate font-medium text-ink">{p.target_name || p.target}</span>
                    <span className="shrink-0 font-mono text-[10px] text-faint">[{p.target_label}]</span>
                  </div>
                  <span className="metric shrink-0 text-sm text-nickel-bright">
                    {Math.round(p.score * 100)}%
                  </span>
                </div>

                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-line/60">
                  <div
                    className="h-full rounded-full bg-copper/70"
                    style={{ width: `${Math.max(4, Math.round(p.score * 100))}%` }}
                  />
                </div>

                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-faint">
                  <Lightbulb size={12} className="shrink-0 text-copper/80" />
                  <span className="truncate">{p.reason}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 font-mono text-[10px] text-faint/80">
                  <span>общих: {p.shared_neighbors}</span>
                  <span>AA {p.adamic_adar.toFixed(2)}</span>
                  <span>Jaccard {p.jaccard.toFixed(2)}</span>
                  <span>RA {p.resource_allocation.toFixed(2)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        {pred.data && pred.data.count > 0 && (
          <div className="mt-4 flex items-center gap-1.5 text-[11px] text-faint">
            <Sparkles size={12} className="text-copper" /> {pred.data.count} вероятных связей от «
            {pred.data.seed.name || pred.data.seed.id}» · метрика {metric}
          </div>
        )}
      </div>
    </div>
  );
}
