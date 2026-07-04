import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeftRight, Cpu, Lightbulb, Link2, Radar, Sparkles, TriangleAlert } from 'lucide-react';
import { api } from '../api';

// §3.14 GDS nodeSimilarity / KNN — корпусная лента предсказанных недостающих связей.
// В отличие от per-seed подсказок, граф САМ сканирует весь корпус и выдаёт глобально
// сильнейшие пары «очень похожи по соседям, но прямого ребра нет» — killer над картой
// пробелов: не нужно знать, что искать, граф подсказывает следующую связь.

type LabelOpt = { id: string; label: string };

const LABELS: LabelOpt[] = [
  { id: '', label: 'Любой тип' },
  { id: 'Material', label: 'Материалы' },
  { id: 'Lab', label: 'Лаборатории' },
  { id: 'Property', label: 'Свойства' },
  { id: 'ProcessingRegime', label: 'Режимы' },
  { id: 'Equipment', label: 'Оборудование' },
  { id: 'Method', label: 'Методы' },
];

export function MissingLinksBoardView() {
  const [seedLabel, setSeedLabel] = useState('Material');
  const [targetLabel, setTargetLabel] = useState('');

  const board = useQuery({
    queryKey: ['ml-board', seedLabel, targetLabel],
    queryFn: () => api.missingLinksBoard(seedLabel || undefined, targetLabel || undefined),
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">граф предполагает · node-similarity / KNN · §3.14</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Лента недостающих связей</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          Граф сам сканирует весь корпус и находит пары узлов, которые по топологии очень похожи
          (много общих соседей — метрика Jaccard, как в
          <span className="font-mono"> gds.nodeSimilarity</span>), но прямого ребра между ними ещё
          нет. Такая пара — сильнейший кандидат в «недостающую связь». Рёбра не создаются: это
          подсказка, какую связь проверить следующей.
        </p>

        <div className="mb-5 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Одна сторона</span>
            <select
              value={seedLabel}
              onChange={(e) => setSeedLabel(e.target.value)}
              className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {LABELS.map((l) => (
                <option key={l.id || 'any-seed'} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Вторая сторона</span>
            <select
              value={targetLabel}
              onChange={(e) => setTargetLabel(e.target.value)}
              className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {LABELS.map((l) => (
                <option key={l.id || 'any-target'} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          {board.data && (
            <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/50 px-2.5 py-1 text-[10px] uppercase tracking-wide text-faint">
              <Cpu size={11} className="text-copper" />
              {board.data.method === 'gds' ? 'GDS nodeSimilarity' : 'in-process Jaccard'}
            </span>
          )}
        </div>

        {board.isLoading && (
          <div className="flex items-center gap-2 text-sm text-faint">
            <Radar size={15} className="animate-pulse text-copper" /> Граф сканирует корпус и ищет
            сильнейшие неявные связи…
          </div>
        )}
        {board.isError && (
          <div className="flex items-center gap-2 text-sm text-copper">
            <TriangleAlert size={15} /> Не удалось построить ленту.
          </div>
        )}

        {board.data && board.data.count === 0 && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            Нет пар с достаточным сходством для выбранных типов узлов.
          </div>
        )}

        {board.data && board.data.count > 0 && (
          <ul className="space-y-2">
            {board.data.predictions.map((p, i) => (
              <li
                key={`${p.a.id}::${p.b.id}`}
                className="rounded-lg border border-line bg-surface/50 px-4 py-3 transition hover:border-copper/40"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 font-mono text-[10px] text-faint">#{i + 1}</span>
                    <span className="truncate font-medium text-ink">{p.a.name}</span>
                    <ArrowLeftRight size={13} className="shrink-0 text-copper" />
                    <span className="truncate font-medium text-ink">{p.b.name}</span>
                  </div>
                  <span className="metric shrink-0 text-sm text-nickel-bright">
                    {Math.round(p.confidence * 100)}%
                  </span>
                </div>

                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-faint">
                  {p.a.label && (
                    <span className="rounded border border-line/70 bg-surface/40 px-1.5 py-0.5 font-mono">
                      {p.a.label}
                    </span>
                  )}
                  <Link2 size={11} className="text-copper/70" />
                  {p.b.label && (
                    <span className="rounded border border-line/70 bg-surface/40 px-1.5 py-0.5 font-mono">
                      {p.b.label}
                    </span>
                  )}
                  <span className="ml-1">
                    Jaccard {p.similarity.toFixed(3)} · {p.shared} общих
                  </span>
                </div>

                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-line/60">
                  <div
                    className="h-full rounded-full bg-copper/70"
                    style={{ width: `${Math.max(4, Math.round(p.confidence * 100))}%` }}
                  />
                </div>

                <div className="mt-2 flex items-start gap-1.5 text-[11px] text-faint">
                  <Lightbulb size={12} className="mt-0.5 shrink-0 text-copper/80" />
                  <span>{p.reason}</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        {board.data && board.data.count > 0 && (
          <div className="mt-4 flex items-center gap-1.5 text-[11px] text-faint">
            <Sparkles size={12} className="text-copper" /> {board.data.count} предсказанных связей ·
            глобальный рейтинг по всему корпусу · рёбра не создаются
          </div>
        )}
      </div>
    </div>
  );
}
