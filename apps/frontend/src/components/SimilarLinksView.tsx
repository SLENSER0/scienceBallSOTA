import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Cpu, Layers, Lightbulb, Sparkles, TriangleAlert, Users } from 'lucide-react';
import { api } from '../api';

// §3.14 GDS node-similarity / KNN — «граф подсказывает вероятные, но неявные связи».
// Killer над картой пробелов: материалы, похожие на X, связаны с лабораторией L →
// вероятно, X тоже относится к L, хотя ребро не проведено (item-based CF поверх KG).

const TARGETS: { id: string; label: string }[] = [
  { id: 'Lab', label: 'Лаборатории' },
  { id: 'Property', label: 'Свойства' },
  { id: 'ProcessingRegime', label: 'Режимы' },
  { id: 'Equipment', label: 'Оборудование' },
  { id: 'Method', label: 'Методы' },
  { id: '', label: 'Любые узлы' },
];

export function SimilarLinksView() {
  const [seed, setSeed] = useState('');
  const [target, setTarget] = useState('Lab');

  const seeds = useQuery({
    queryKey: ['sl-seeds'],
    queryFn: () => api.simLinksSeeds('Material'),
  });
  const seedId = seed || seeds.data?.seeds[0]?.id || '';

  const sug = useQuery({
    queryKey: ['sl-suggest', seedId, target],
    queryFn: () => api.simLinksSuggest(seedId, target || undefined),
    enabled: !!seedId,
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">граф предполагает · node-similarity / KNN · §3.14</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Вероятные неявные связи</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          Находим узлы, похожие на выбранный (по общим соседям — метрика Jaccard, как в
          <span className="font-mono"> gds.nodeSimilarity</span>), и переносим их связи по аналогии:
          «эта лаборатория, вероятно, работает с этим материалом». Рёбра не создаются — это
          подсказка, какую связь проверить.
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
            <span className="text-[11px] uppercase tracking-wide text-faint">Тип связи</span>
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

          {sug.data && (
            <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/50 px-2.5 py-1 text-[10px] uppercase tracking-wide text-faint">
              <Cpu size={11} className="text-copper" />
              {sug.data.method === 'gds' ? 'GDS nodeSimilarity' : 'in-process Jaccard'}
            </span>
          )}
        </div>

        {sug.isLoading && <div className="text-sm text-faint">Граф ищет похожих и переносит связи…</div>}
        {sug.isError && (
          <div className="flex items-center gap-2 text-sm text-copper">
            <TriangleAlert size={15} /> Не удалось получить подсказки.
          </div>
        )}

        {sug.data && sug.data.count === 0 && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            Нет похожих узлов с переносимыми связями для выбранных фильтров.
          </div>
        )}

        {sug.data && sug.data.count > 0 && (
          <ul className="space-y-2">
            {sug.data.suggestions.map((s) => (
              <li
                key={s.target}
                className="rounded-lg border border-line bg-surface/50 px-4 py-3 transition hover:border-copper/40"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <Layers size={15} className="shrink-0 text-copper" />
                    <span className="truncate font-medium text-ink">{s.target_name || s.target}</span>
                    <span className="shrink-0 font-mono text-[10px] text-faint">[{s.target_label}]</span>
                  </div>
                  <span className="metric shrink-0 text-sm text-nickel-bright">
                    {Math.round(s.score * 100)}%
                  </span>
                </div>

                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-line/60">
                  <div
                    className="h-full rounded-full bg-copper/70"
                    style={{ width: `${Math.max(4, Math.round(s.score * 100))}%` }}
                  />
                </div>

                <div className="mt-2 flex items-start gap-1.5 text-[11px] text-faint">
                  <Lightbulb size={12} className="mt-0.5 shrink-0 text-copper/80" />
                  <span>{s.reason}</span>
                </div>

                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-faint/80">
                  <Users size={11} className="shrink-0" />
                  {s.supporters.slice(0, 4).map((p) => (
                    <span
                      key={p.id}
                      className="rounded border border-line/70 bg-surface/40 px-1.5 py-0.5 font-mono"
                    >
                      {p.name} · {p.similarity.toFixed(2)}
                    </span>
                  ))}
                  {s.support_count > 4 && <span>+{s.support_count - 4}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}

        {sug.data && sug.data.count > 0 && (
          <div className="mt-4 flex items-center gap-1.5 text-[11px] text-faint">
            <Sparkles size={12} className="text-copper" /> {sug.data.count} вероятных связей от «
            {sug.data.seed.name || sug.data.seed.id}» · по аналогии с похожими узлами
          </div>
        )}
      </div>
    </div>
  );
}
