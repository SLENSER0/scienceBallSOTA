import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, Gauge, Loader2, Plus, Trophy, X } from 'lucide-react';
import { api, type HardnessCompareResult, type HardnessEquivalents } from '../api';

// Cross-scale hardness comparison HV↔HRC↔HB (ASTM E140) — §7.3.
// The corpus reports hardness on three incompatible scales; here the already-built
// converter is put to work so «30 HRC ≈ 302 HV ≈ 286 HB» line up and can be ranked.

const SCALES = ['HV', 'HB', 'HRC'] as const;
type Scale = (typeof SCALES)[number];

interface ReadingInput {
  label: string;
  value: string;
  scale: Scale;
}

const SCALE_LABEL: Record<Scale, string> = {
  HV: 'Vickers (HV)',
  HB: 'Brinell (HB)',
  HRC: 'Rockwell C (HRC)',
};

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export function HardnessCompareView() {
  // -- Single-reading equivalence («переводчик шкал») ------------------------
  const [value, setValue] = useState('30');
  const [scale, setScale] = useState<Scale>('HRC');
  const equiv = useMutation<HardnessEquivalents, Error, void>({
    mutationFn: () => api.hardnessEquivalents(Number(value), scale),
  });

  // -- Multi-reading leaderboard --------------------------------------------
  const [rows, setRows] = useState<ReadingInput[]>([
    { label: 'Сталь A', value: '30', scale: 'HRC' },
    { label: 'Сталь B', value: '302', scale: 'HV' },
    { label: 'Сталь C', value: '286', scale: 'HB' },
  ]);
  const [target, setTarget] = useState<Scale>('HV');
  const cmp = useMutation<HardnessCompareResult, Error, void>({
    mutationFn: () =>
      api.hardnessCompare(
        rows
          .filter((r) => r.value.trim() !== '')
          .map((r) => ({ label: r.label, value: Number(r.value), scale: r.scale })),
        target,
      ),
  });

  const setRow = (i: number, patch: Partial<ReadingInput>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, { label: '', value: '', scale: 'HV' }]);
  const delRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">кросс-шкальная твёрдость · ASTM E140</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Сравнение твёрдости HV ↔ HRC ↔ HB</h2>
        <p className="mb-6 max-w-2xl text-sm text-muted">
          Шкалы твёрдости нелинейны и напрямую несравнимы. Здесь значения приводятся к общей
          шкале по стандартной таблице ASTM E140 (сталь, интерполяция) — приблизительно, с
          сохранением исходной шкалы.
        </p>

        {/* -- Scale translator ------------------------------------------- */}
        <div className="panel mb-8 p-4">
          <div className="eyebrow mb-3 text-faint">Переводчик шкал</div>
          <div className="flex flex-wrap items-end gap-2">
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              type="number"
              className="metric w-28 rounded-md border border-line bg-surface/60 px-3 py-2 text-lg text-nickel-bright focus:border-copper/50 focus:outline-none"
              placeholder="30"
            />
            <select
              value={scale}
              onChange={(e) => setScale(e.target.value as Scale)}
              className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {SCALES.map((s) => (
                <option key={s} value={s}>
                  {SCALE_LABEL[s]}
                </option>
              ))}
            </select>
            <button
              onClick={() => value.trim() && equiv.mutate()}
              disabled={equiv.isPending || value.trim() === ''}
              className="btn-copper flex items-center gap-1.5"
            >
              {equiv.isPending ? <Gauge size={16} className="animate-spin" /> : <ArrowRight size={16} />}
              Перевести
            </button>
          </div>

          {equiv.data && (
            <div className="mt-4">
              <div className="flex flex-wrap items-center gap-2">
                {equiv.data.equivalents.map((e) => (
                  <div
                    key={e.scale}
                    className={`flex flex-col items-center rounded-md border px-4 py-2 ${
                      e.is_source
                        ? 'border-copper/50 bg-copper/10'
                        : 'border-line bg-surface/40'
                    }`}
                  >
                    <span className="metric text-xl text-nickel-bright">{fmt(e.value)}</span>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-faint">
                      {e.scale}
                    </span>
                  </div>
                ))}
                {equiv.data.tensile_mpa != null && (
                  <div className="flex flex-col items-center rounded-md border border-line bg-surface/40 px-4 py-2">
                    <span className="metric text-xl text-nickel-bright">
                      ≈ {fmt(equiv.data.tensile_mpa)}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-faint">
                      МПа · σ_UTS
                    </span>
                  </div>
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-faint">
                <span className="chip text-copper/80">{equiv.data.conversion_standard}</span>
                {equiv.data.approximate && <span className="chip text-gap">приблизительно</span>}
                <span className="font-mono">normalization_method={equiv.data.normalization_method}</span>
              </div>
            </div>
          )}
          {equiv.error && (
            <div className="mt-3 text-sm text-contradiction">{equiv.error.message}</div>
          )}
        </div>

        {/* -- Cross-scale leaderboard ------------------------------------ */}
        <div className="mb-3 flex items-center gap-2">
          <div className="eyebrow text-faint">Таблица сравнения · приведение к общей шкале</div>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-faint">общая шкала</span>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value as Scale)}
              className="rounded-md border border-line bg-surface/60 px-2 py-1 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {SCALES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="panel mb-3 p-3">
          <div className="flex flex-col gap-2">
            {rows.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={r.label}
                  onChange={(e) => setRow(i, { label: e.target.value })}
                  placeholder={`строка ${i + 1}`}
                  className="flex-1 rounded-md border border-line bg-surface/60 px-3 py-1.5 text-sm text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
                />
                <input
                  value={r.value}
                  onChange={(e) => setRow(i, { value: e.target.value })}
                  type="number"
                  placeholder="значение"
                  className="metric w-28 rounded-md border border-line bg-surface/60 px-3 py-1.5 text-sm text-nickel-bright focus:border-copper/50 focus:outline-none"
                />
                <select
                  value={r.scale}
                  onChange={(e) => setRow(i, { scale: e.target.value as Scale })}
                  className="rounded-md border border-line bg-surface/60 px-2 py-1.5 text-sm text-ink focus:border-copper/50 focus:outline-none"
                >
                  {SCALES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => delRow(i)}
                  disabled={rows.length <= 1}
                  className="text-faint transition hover:text-contradiction disabled:opacity-30"
                  title="Удалить строку"
                >
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={addRow}
              className="chip text-faint hover:border-copper/40 hover:text-copper"
            >
              <Plus size={12} /> строка
            </button>
            <button
              onClick={() => cmp.mutate()}
              disabled={cmp.isPending}
              className="btn-copper ml-auto flex items-center gap-1.5"
            >
              {cmp.isPending ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
              Сравнить
            </button>
          </div>
        </div>

        {cmp.error && <div className="text-sm text-contradiction">{cmp.error.message}</div>}

        {cmp.data && (
          <>
            {cmp.data.hardest && (
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                <span className="chip border-copper/40 text-copper">
                  <Trophy size={12} /> самый твёрдый: {cmp.data.hardest}
                </span>
                {cmp.data.spread_hv != null && (
                  <span className="chip text-faint">разброс ≈ {fmt(cmp.data.spread_hv)} HV</span>
                )}
                <span className="chip text-copper/80">{cmp.data.conversion_standard}</span>
              </div>
            )}
            <div className="panel overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="font-mono text-[11px] uppercase tracking-wide text-faint">
                    <th className="px-3 py-2 text-left">строка</th>
                    <th className="px-3 py-2 text-right">исходно</th>
                    <th className="px-3 py-2 text-right">→ {cmp.data.target_scale}</th>
                    <th className="px-3 py-2 text-right">HV</th>
                    <th className="px-3 py-2 text-right">σ_UTS, МПа</th>
                  </tr>
                </thead>
                <tbody>
                  {cmp.data.rows.map((row, i) => (
                    <tr
                      key={i}
                      className={`border-t border-line/60 ${
                        row.label === cmp.data!.hardest ? 'bg-copper/5' : ''
                      }`}
                    >
                      <td className="px-3 py-2 text-ink/90">{row.label}</td>
                      <td className="px-3 py-2 text-right text-muted">
                        <span className="metric">{fmt(row.original_value)}</span>{' '}
                        <span className="font-mono text-[10px] text-faint">{row.original_scale}</span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className="metric text-nickel-bright">{fmt(row.normalized_value)}</span>
                      </td>
                      <td className="px-3 py-2 text-right metric text-muted">{fmt(row.hv)}</td>
                      <td className="px-3 py-2 text-right metric text-muted">{fmt(row.tensile_mpa)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[11px] text-faint">
              Значения приблизительны (сталь, ASTM E140). Ранжирование выполнено по канонической
              шкале HV; исходная шкала сохранена.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
