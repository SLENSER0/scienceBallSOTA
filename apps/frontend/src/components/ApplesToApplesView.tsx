import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, Loader2, Plus, Scale, TriangleAlert, X } from 'lucide-react';
import { api, type NormalizeResult } from '../api';

// Apples-to-apples: normalized units in the Comparison table — §7.5.
// Values from different sources arrive on different units (ksi / N·mm⁻² / GPa / MPa)
// and are incomparable at a glance. Here every cell is projected onto one canonical
// unit (strength → MPa) so the column reads honestly and can be ranked.

interface RowInput {
  label: string;
  value: string;
  unit: string;
}

const EXAMPLE_ROWS: RowInput[] = [
  { label: 'Источник A (ASTM datasheet)', value: '46.5', unit: 'ksi' },
  { label: 'Источник B (ГОСТ)', value: '320', unit: 'N/mm²' },
  { label: 'Источник C (обзор)', value: '0.32', unit: 'GPa' },
  { label: 'Источник D (справочник)', value: '340', unit: 'MPa' },
];

const TARGETS = ['авто', 'MPa', '°C', 'mm', 'kJ', '%'] as const;

const METHOD_LABEL: Record<string, string> = {
  direct: 'как есть',
  converted: 'пересчитано',
  incompatible: 'несовместимо',
  unit_missing: 'нет единицы',
};

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return String(v);
}

export function ApplesToApplesView() {
  const [rows, setRows] = useState<RowInput[]>(EXAMPLE_ROWS);
  const [target, setTarget] = useState<(typeof TARGETS)[number]>('авто');

  const norm = useMutation<NormalizeResult, Error, void>({
    mutationFn: () =>
      api.comparisonNormalize(
        rows
          .filter((r) => r.value.trim() !== '')
          .map((r) => ({ label: r.label.trim(), value: Number(r.value), unit: r.unit.trim() })),
        target === 'авто' ? undefined : target,
      ),
  });

  const setRow = (i: number, patch: Partial<RowInput>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, { label: '', value: '', unit: '' }]);
  const delRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));

  const result = norm.data;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">apples-to-apples · единые единицы · §7.5</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Нормализованные единицы в Сравнении
        </h2>
        <p className="mb-6 max-w-2xl text-sm text-muted">
          Значения из разных источников приходят в разных единицах (<code>ksi</code>,{' '}
          <code>N·mm⁻²</code>, <code>GPa</code>, <code>MPa</code>) и на глаз несравнимы. Здесь
          каждая ячейка приводится к одной канонической единице — прочность → <b>MPa</b> — так
          таблица сравнения становится честной.
        </p>

        {/* -- Input rows --------------------------------------------------- */}
        <div className="panel mb-4 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="eyebrow text-faint">Ячейки сравнения</div>
            <label className="flex items-center gap-2 text-xs text-muted">
              приводить к
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value as (typeof TARGETS)[number])}
                className="rounded-md border border-line bg-surface/60 px-2 py-1 text-sm text-ink focus:border-copper/50 focus:outline-none"
              >
                {TARGETS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="space-y-2">
            {rows.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={r.label}
                  onChange={(e) => setRow(i, { label: e.target.value })}
                  placeholder="источник / материал"
                  className="min-w-0 flex-1 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
                />
                <input
                  value={r.value}
                  onChange={(e) => setRow(i, { value: e.target.value })}
                  type="number"
                  placeholder="0"
                  className="metric w-24 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-nickel-bright focus:border-copper/50 focus:outline-none"
                />
                <input
                  value={r.unit}
                  onChange={(e) => setRow(i, { unit: e.target.value })}
                  placeholder="ksi"
                  className="w-24 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
                />
                <button
                  onClick={() => delRow(i)}
                  className="rounded-md p-2 text-faint hover:bg-surface/60 hover:text-ink"
                  aria-label="удалить строку"
                >
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>

          <div className="mt-3 flex items-center justify-between">
            <button
              onClick={addRow}
              className="flex items-center gap-1.5 text-sm text-muted hover:text-ink"
            >
              <Plus size={15} /> строка
            </button>
            <button
              onClick={() => norm.mutate()}
              disabled={norm.isPending || rows.every((r) => r.value.trim() === '')}
              className="btn-copper flex items-center gap-1.5"
            >
              {norm.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Scale size={16} />
              )}
              Привести к единой единице
            </button>
          </div>
        </div>

        {norm.isError && (
          <div className="panel mb-4 flex items-center gap-2 border-rust/40 p-3 text-sm text-rust">
            <TriangleAlert size={16} /> Не удалось нормализовать: {norm.error.message}
          </div>
        )}

        {/* -- Result table ------------------------------------------------- */}
        {result && (
          <div className="panel overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <div className="text-sm text-muted">
                Единая единица колонки:{' '}
                <b className="text-ink">{result.target_unit ?? '—'}</b>
              </div>
              {result.spread !== null && result.spread !== undefined && (
                <div className="text-xs text-faint">
                  разброс {fmt(result.min)}…{fmt(result.max)} {result.target_unit} (Δ{' '}
                  {fmt(result.spread)})
                </div>
              )}
            </div>

            {!result.all_comparable && (
              <div className="flex items-center gap-2 border-b border-line bg-rust/5 px-4 py-2 text-xs text-rust">
                <TriangleAlert size={14} /> некоторые ячейки не приводятся к{' '}
                {result.target_unit} — они помечены и исключены из ранжирования
              </div>
            )}

            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-faint">
                  <th className="px-4 py-2 font-medium">Источник</th>
                  <th className="px-4 py-2 font-medium">Исходное</th>
                  <th className="px-4 py-2 font-medium">
                    Нормализовано ({result.target_unit ?? '—'})
                  </th>
                  <th className="px-4 py-2 font-medium">Метод</th>
                </tr>
              </thead>
              <tbody>
                {result.cells.map((c, i) => {
                  const isBest = c.label && c.label === result.best_label;
                  const isWorst = c.label && c.label === result.worst_label;
                  const bad =
                    c.normalization_method === 'incompatible' ||
                    c.normalization_method === 'unit_missing';
                  return (
                    <tr key={i} className="border-b border-line/60 last:border-0">
                      <td className="px-4 py-2 text-ink">{c.label || `#${i + 1}`}</td>
                      <td className="px-4 py-2 text-muted">
                        <span className="metric text-nickel-bright">{fmt(c.value_raw)}</span>{' '}
                        {c.unit || <span className="text-faint">без единицы</span>}
                      </td>
                      <td className="px-4 py-2">
                        {bad ? (
                          <span className="text-rust">—</span>
                        ) : (
                          <span className="metric text-lg font-semibold text-nickel-bright">
                            {fmt(c.value_normalized)}
                            <span className="ml-1 text-xs font-normal text-faint">
                              {c.normalized_unit}
                            </span>
                            {isBest && (
                              <span className="ml-2 rounded bg-copper/15 px-1.5 py-0.5 text-[10px] uppercase text-copper">
                                макс
                              </span>
                            )}
                            {isWorst && !isBest && (
                              <span className="ml-2 rounded bg-surface px-1.5 py-0.5 text-[10px] uppercase text-faint">
                                мин
                              </span>
                            )}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className={`text-xs ${bad ? 'text-rust' : c.normalization_method === 'converted' ? 'text-copper' : 'text-faint'}`}
                        >
                          {METHOD_LABEL[c.normalization_method] ?? c.normalization_method}
                        </span>
                        {c.note && <div className="mt-0.5 text-[11px] text-faint">{c.note}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!result && !norm.isPending && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-muted">
            <ArrowRight size={16} /> Введите значения из разных источников и приведите их к
            одной единице.
          </div>
        )}
      </div>
    </div>
  );
}
