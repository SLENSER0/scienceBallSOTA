import { useEffect, useMemo, useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { Loader2, SlidersHorizontal, Thermometer, Clock, RotateCcw, Layers } from 'lucide-react';

// §4.7 — Числовые range-фасеты: гистограммы temperature_c / time_h + двуручьевые
// слайдеры. Бэкенд GET /api/v1/range-facets/histogram строит распределения
// параметров ProcessingRegime→HAS_PARAMETER→Parameter по всему корпусу, отдаёт
// бины (с флагом selected и пересчётом selectedCount), список операций-фасет и
// список подходящих режимов (cross-filter по обоим диапазонам сразу).

interface HistBin {
  lo: number;
  hi: number;
  count: number;
  selected: boolean;
}
interface FieldHist {
  field: string;
  label: string;
  unit: string;
  count: number;
  min: number | null;
  max: number | null;
  domainMin: number | null;
  domainMax: number | null;
  selectedMin: number | null;
  selectedMax: number | null;
  selectedCount: number;
  bins: HistBin[];
}
interface MatchedRegime {
  id: string;
  operation: string;
  name: string;
  domain: string | null;
  tempCount: number;
  tempMin: number | null;
  tempMax: number | null;
  timeCount: number;
  timeMin: number | null;
  timeMax: number | null;
  paramCount: number;
  chunks: number;
}
interface RangeFacetResponse {
  fields: Record<string, FieldHist>;
  operations: { operation: string; count: number }[];
  matched: { count: number; regimes: MatchedRegime[] };
  filters: Record<string, unknown>;
  totalRegimes: number;
}

// Границы выбранных диапазонов слайдеров (undefined = не ограничено).
interface RangeSel {
  tempMin?: number;
  tempMax?: number;
  timeMin?: number;
  timeMax?: number;
}

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

async function fetchHistogram(operation: string, sel: RangeSel): Promise<RangeFacetResponse> {
  const p = new URLSearchParams();
  p.set('bins', '18');
  if (operation) p.set('operation', operation);
  if (sel.tempMin != null) p.set('temp_min', String(sel.tempMin));
  if (sel.tempMax != null) p.set('temp_max', String(sel.tempMax));
  if (sel.timeMin != null) p.set('time_min', String(sel.timeMin));
  if (sel.timeMax != null) p.set('time_max', String(sel.timeMax));
  const res = await fetch(`/api/v1/range-facets/histogram?${p.toString()}`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<RangeFacetResponse>;
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
  return String(v);
}

// Двуручьевой слайдер поверх гистограммы. Две перекрывающихся <input range>;
// выбранное окно подсвечивается, промежуточные значения защёлкиваются на границы.
function HistogramSlider({
  hist,
  selLo,
  selHi,
  onChange,
}: {
  hist: FieldHist;
  selLo: number | undefined;
  selHi: number | undefined;
  onChange: (lo: number | undefined, hi: number | undefined) => void;
}) {
  const dMin = hist.domainMin ?? 0;
  const dMax = hist.domainMax ?? 1;
  const span = dMax - dMin || 1;
  const step = span / 200;
  const lo = selLo ?? dMin;
  const hi = selHi ?? dMax;
  const maxCount = Math.max(1, ...hist.bins.map((b) => b.count));
  const pct = (v: number) => ((v - dMin) / span) * 100;
  const active = selLo != null || selHi != null;

  if (hist.count === 0) {
    return (
      <div className="panel p-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          {hist.field === 'temperature_c' ? (
            <Thermometer size={15} className="text-copper" />
          ) : (
            <Clock size={15} className="text-copper" />
          )}
          {hist.label}
        </div>
        <div className="mt-3 font-mono text-[10px] text-faint">нет значений в корпусе</div>
      </div>
    );
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2">
        {hist.field === 'temperature_c' ? (
          <Thermometer size={15} className="text-copper" />
        ) : (
          <Clock size={15} className="text-copper" />
        )}
        <span className="text-sm text-nickel">{hist.label}</span>
        <span className="font-mono text-[10px] text-faint">
          {hist.count} значений · домен {fmt(hist.domainMin)}…{fmt(hist.domainMax)} {hist.unit}
        </span>
        {active && (
          <button
            onClick={() => onChange(undefined, undefined)}
            className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] text-faint underline decoration-dotted hover:text-nickel"
          >
            <RotateCcw size={10} /> сброс
          </button>
        )}
      </div>

      {/* Гистограмма: выбранные бины ярче */}
      <div className="mt-3 flex h-24 items-end gap-[2px]">
        {hist.bins.map((b, i) => (
          <div
            key={i}
            title={`${fmt(b.lo)}…${fmt(b.hi)} ${hist.unit}: ${b.count}`}
            className="flex-1 rounded-t-sm transition-colors"
            style={{
              height: `${Math.max(3, (b.count / maxCount) * 100)}%`,
              background: b.selected
                ? 'rgba(200,121,65,0.85)'
                : 'rgba(200,121,65,0.22)',
            }}
          />
        ))}
      </div>

      {/* Двуручьевой слайдер */}
      <div className="relative mt-3 h-5">
        <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded bg-surface" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded bg-copper/60"
          style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }}
        />
        <input
          type="range"
          min={dMin}
          max={dMax}
          step={step}
          value={lo}
          onChange={(e) => {
            const v = Math.min(Number(e.target.value), hi);
            onChange(v <= dMin ? undefined : v, selHi);
          }}
          className="range-thumb pointer-events-none absolute left-0 top-0 h-5 w-full appearance-none bg-transparent"
        />
        <input
          type="range"
          min={dMin}
          max={dMax}
          step={step}
          value={hi}
          onChange={(e) => {
            const v = Math.max(Number(e.target.value), lo);
            onChange(selLo, v >= dMax ? undefined : v);
          }}
          className="range-thumb pointer-events-none absolute left-0 top-0 h-5 w-full appearance-none bg-transparent"
        />
      </div>

      <div className="mt-1 flex items-center justify-between font-mono text-[10px] text-faint">
        <span className={active ? 'text-copper' : ''}>
          {fmt(Math.round(lo * 100) / 100)} {hist.unit}
        </span>
        <span>
          в окне: <span className="text-nickel">{hist.selectedCount}</span> / {hist.count}
        </span>
        <span className={active ? 'text-copper' : ''}>
          {fmt(Math.round(hi * 100) / 100)} {hist.unit}
        </span>
      </div>
    </div>
  );
}

export function RangeFacetsView() {
  const [operation, setOperation] = useState('');
  const [sel, setSel] = useState<RangeSel>({});
  // Локальное состояние слайдеров, чтобы UI отзывался мгновенно, а запрос летел
  // после отпускания (debounce): держим «черновик» и коммитим его через таймер.
  const [draft, setDraft] = useState<RangeSel>({});

  useEffect(() => {
    const t = setTimeout(() => setSel(draft), 220);
    return () => clearTimeout(t);
  }, [draft]);

  const q = useQuery<RangeFacetResponse>({
    queryKey: ['range-facets', operation, sel],
    queryFn: () => fetchHistogram(operation, sel),
    placeholderData: keepPreviousData,
  });

  const data = q.data;
  const temp = data?.fields?.temperature_c;
  const time = data?.fields?.time_h;
  const matched = data?.matched?.regimes ?? [];
  const activeFilters = useMemo(
    () =>
      Object.values(draft).filter((v) => v != null).length + (operation ? 1 : 0),
    [draft, operation],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <style>{`
        .range-thumb::-webkit-slider-thumb{-webkit-appearance:none;pointer-events:auto;height:16px;width:16px;border-radius:9999px;background:#C87941;border:2px solid #181C25;cursor:pointer;}
        .range-thumb::-moz-range-thumb{pointer-events:auto;height:16px;width:16px;border-radius:9999px;background:#C87941;border:2px solid #181C25;cursor:pointer;}
      `}</style>

      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <SlidersHorizontal size={16} className="text-copper" /> Числовые range-фасеты
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          гистограммы temperature_c / time_h · двуручьевые слайдеры · cross-filter · §4.7
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 font-mono text-[10px] text-faint">
            <Layers size={12} /> операция:
          </label>
          <select
            value={operation}
            onChange={(e) => setOperation(e.target.value)}
            className="rounded-md border border-line bg-surface/60 px-2 py-1 text-xs text-nickel focus:border-copper/50 focus:outline-none"
          >
            <option value="">все ({data?.totalRegimes ?? 0} режимов)</option>
            {(data?.operations ?? []).map((o) => (
              <option key={o.operation} value={o.operation}>
                {o.operation} ({o.count})
              </option>
            ))}
          </select>
          {activeFilters > 0 && (
            <button
              onClick={() => {
                setOperation('');
                setDraft({});
              }}
              className="inline-flex items-center gap-1 font-mono text-[10px] text-faint underline decoration-dotted hover:text-nickel"
            >
              <RotateCcw size={10} /> сбросить всё
            </button>
          )}
          {q.isFetching && (
            <Loader2 size={12} className="animate-spin text-copper" />
          )}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-0 overflow-hidden">
        {/* Слева — слайдеры/гистограммы */}
        <div className="min-h-0 space-y-4 overflow-y-auto border-r border-line p-4">
          {q.isLoading && !data ? (
            <div className="flex items-center gap-2 font-mono text-[10px] text-faint">
              <Loader2 size={12} className="animate-spin text-copper" /> строю гистограммы…
            </div>
          ) : q.isError ? (
            <div className="text-sm text-contradiction">Не удалось загрузить распределения.</div>
          ) : (
            <>
              {temp && (
                <HistogramSlider
                  hist={temp}
                  selLo={draft.tempMin}
                  selHi={draft.tempMax}
                  onChange={(lo, hi) => setDraft((d) => ({ ...d, tempMin: lo, tempMax: hi }))}
                />
              )}
              {time && (
                <HistogramSlider
                  hist={time}
                  selLo={draft.timeMin}
                  selHi={draft.timeMax}
                  onChange={(lo, hi) => setDraft((d) => ({ ...d, timeMin: lo, timeMax: hi }))}
                />
              )}
            </>
          )}
        </div>

        {/* Справа — подходящие режимы (cross-filter) */}
        <div className="min-h-0 overflow-y-auto p-4">
          <div className="mb-3 flex items-center gap-2 font-mono text-[10px] text-faint">
            <span>
              подходящих режимов: <span className="text-nickel">{data?.matched?.count ?? 0}</span>
            </span>
            {data && data.matched.count > matched.length && (
              <span>· показаны первые {matched.length}</span>
            )}
          </div>

          {matched.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <SlidersHorizontal size={28} className="mx-auto mb-2 text-faint" />
                <div className="font-mono text-xs text-faint">
                  нет режимов в выбранных диапазонах — расширьте окна слайдеров
                </div>
              </div>
            </div>
          ) : (
            <div className="grid gap-2">
              {matched.map((r) => (
                <div key={r.id} className="panel p-3">
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm text-nickel">{r.name}</span>
                    <span className="chip shrink-0 border-line text-[9px] text-faint">
                      {r.operation}
                    </span>
                    {r.chunks > 0 && (
                      <span className="shrink-0 font-mono text-[10px] text-faint">
                        {r.chunks} чанк.
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-3 font-mono text-[10px] text-faint">
                    {r.tempCount > 0 && (
                      <span className="inline-flex items-center gap-1">
                        <Thermometer size={10} className="text-copper" />
                        {fmt(r.tempMin)}…{fmt(r.tempMax)} °C
                        {r.tempCount > 1 && <span className="text-faint">×{r.tempCount}</span>}
                      </span>
                    )}
                    {r.timeCount > 0 && (
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} className="text-copper" />
                        {fmt(r.timeMin)}…{fmt(r.timeMax)} ч
                        {r.timeCount > 1 && <span className="text-faint">×{r.timeCount}</span>}
                      </span>
                    )}
                    {r.domain && <span className="ml-auto">{r.domain}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
