import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, CircleCheck, CircleSlash, Loader2 } from 'lucide-react';
import { api } from '../api';

type Cell = { value?: number; unit?: string; gap?: boolean; evidence_ids?: string[] };

const EXAMPLES = [
  'методы обессоливания воды: обратный осмос, ионный обмен, электродиализ',
  'методы удаления SO2 из отходящих газов',
];

export function CompareView() {
  const [q, setQ] = useState('');
  const cmp = useMutation({ mutationFn: (query: string) => api.comparison(query) });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">сравнительный анализ технологий</div>
        <h2 className="mb-4 font-display text-2xl font-semibold">Таблица сравнения</h2>

        <div className="panel mb-4 flex items-end gap-2 p-1.5">
          <textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            rows={2}
            placeholder="Технологии для сравнения (материал / процесс / условия)…"
            className="min-h-[48px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-ink placeholder:text-faint focus:outline-none"
          />
          <button
            onClick={() => q.trim() && cmp.mutate(q.trim())}
            disabled={cmp.isPending || !q.trim()}
            className="btn-copper mb-1 mr-1 flex items-center gap-1.5"
          >
            {cmp.isPending ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
            Сравнить
          </button>
        </div>

        {!cmp.data && !cmp.isPending && (
          <div className="flex flex-col gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setQ(ex);
                  cmp.mutate(ex);
                }}
                className="rounded-md border border-line bg-surface/40 px-3 py-2 text-left text-sm text-muted hover:border-copper/40 hover:text-ink"
              >
                {ex}
              </button>
            ))}
          </div>
        )}

        {cmp.data && (
          <>
            <div className="eyebrow mb-2">
              покрытие: {cmp.data.coverage.cells_with_evidence}/{cmp.data.coverage.cells_total} ячеек
              с доказательствами · {cmp.data.coverage.solutions} решений
            </div>
            <div className="panel overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    {cmp.data.columns.map((c) => (
                      <th
                        key={c}
                        className="whitespace-nowrap px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wide text-faint"
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cmp.data.rows.map((row, i) => (
                    <tr key={i} className="border-t border-line/60">
                      {cmp.data!.columns.map((c) => (
                        <td key={c} className="px-3 py-2 align-top">
                          <CellValue value={row[c]} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CellValue({ value }: { value: unknown }) {
  if (typeof value === 'string') return <span className="text-ink/90">{value}</span>;
  const cell = value as Cell;
  if (!cell || typeof cell !== 'object') return <span className="text-faint">—</span>;
  if (cell.gap)
    return (
      <span className="chip border-gap/40 text-gap" title="Нет данных (пробел)">
        <CircleSlash size={11} /> пробел
      </span>
    );
  return (
    <span className="flex items-center gap-1.5">
      <span className="metric text-nickel-bright">
        {cell.value}
        {cell.unit ? ` ${cell.unit}` : ''}
      </span>
      {cell.evidence_ids && cell.evidence_ids.length > 0 && (
        <CircleCheck size={12} className="text-verified" />
      )}
    </span>
  );
}
