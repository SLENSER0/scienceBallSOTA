import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertOctagon,
  Loader2,
  RefreshCw,
  Ruler,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-react';
import { api } from '../api';

// §7.7 — Suspect-value flags (SUSPECT_VALUE / statistical_outlier / unit_scale_suspect)
// surfaced in the curation review queue. The units library already computes these
// anomaly signals; here a curator sees «подозрительное значение» badges at a glance
// and OCR / unit-scale blunders (0.32 where the source meant 320 MPa) get caught.

export interface SuspectBadge {
  flag: string; // SUSPECT_VALUE | statistical_outlier | unit_scale_suspect
  severity: string; // hard_error | suspect | outlier | scale
  label_ru: string;
  reason: string;
}

export interface SuspectMeasurement {
  id: string;
  name: string | null;
  property_name: string | null;
  property_id: string | null;
  material: string | null;
  material_class: string | null;
  domain: string | null;
  value: number;
  unit: string | null;
  value_raw: string | null;
  badges: SuspectBadge[];
  indexable: boolean;
  hard_min: number | null;
  hard_max: number | null;
  typical_min: number | null;
  typical_max: number | null;
  robust_z: number | null;
  cohort_median: number | null;
  cohort_n: number;
  suggested_factor: number | null;
  corrected_value: number | null;
}

export interface SuspectQueueResponse {
  total_measurements: number;
  flagged: number;
  counts: Record<string, number>;
  items: SuspectMeasurement[];
}

const FLAG_META: Record<
  string,
  { short: string; icon: typeof TriangleAlert; ru: string }
> = {
  SUSPECT_VALUE: { short: 'диапазон', icon: TriangleAlert, ru: 'подозрительное значение' },
  statistical_outlier: { short: 'выброс', icon: Activity, ru: 'статистический выброс' },
  unit_scale_suspect: { short: 'масштаб', icon: Ruler, ru: 'ошибка масштаба ×10/×100/×1000' },
};

// Badge palette by severity — hard errors read as danger, the rest as caution.
function sevClasses(sev: string): string {
  switch (sev) {
    case 'hard_error':
      return 'border-rust/50 bg-rust/10 text-rust';
    case 'suspect':
      return 'border-copper/50 bg-copper/10 text-copper';
    case 'outlier':
      return 'border-nickel/40 bg-nickel/10 text-nickel-bright';
    default:
      return 'border-line bg-surface/60 text-muted';
  }
}

const FLAGS = ['SUSPECT_VALUE', 'statistical_outlier', 'unit_scale_suspect'] as const;

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return String(v);
}

export function SuspectValuesView() {
  const [flag, setFlag] = useState<string | null>(null);

  const q = useQuery<SuspectQueueResponse, Error>({
    queryKey: ['suspect-values', flag],
    queryFn: () => api.suspectValueQueue(flag ?? undefined),
  });

  const data = q.data;
  const counts = data?.counts ?? {};

  const items = useMemo(() => data?.items ?? [], [data]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">sanity-checks · детект выбросов · §7.7</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Подозрительные значения — очередь курирования
        </h2>
        <p className="mb-6 max-w-3xl text-sm text-muted">
          Три сигнала §7.7 на живых измерениях графа: <b>SUSPECT_VALUE</b> (значение вне
          физического диапазона / типичной полосы), <b>statistical_outlier</b> (выброс в своей
          когорте по robust z-score / IQR) и <b>unit_scale_suspect</b> (путаница масштаба, напр.{' '}
          <code>0.32</code> вместо <code>320&nbsp;MPa</code>). Нефизичные значения не индексируются
          как валидные и уходят на ревью.
        </p>

        {/* -- Summary + filter chips -------------------------------------- */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <button
            onClick={() => setFlag(null)}
            className={`rounded-full border px-3 py-1 text-xs ${
              flag === null
                ? 'border-copper/60 bg-copper/10 text-copper'
                : 'border-line text-muted hover:text-ink'
            }`}
          >
            все флаги{data ? ` · ${data.flagged}` : ''}
          </button>
          {FLAGS.map((f) => {
            const M = FLAG_META[f];
            const Icon = M.icon;
            return (
              <button
                key={f}
                onClick={() => setFlag(flag === f ? null : f)}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                  flag === f
                    ? 'border-copper/60 bg-copper/10 text-copper'
                    : 'border-line text-muted hover:text-ink'
                }`}
              >
                <Icon size={13} /> {M.short}
                <span className="text-faint">{counts[f] ?? 0}</span>
              </button>
            );
          })}
          <button
            onClick={() => q.refetch()}
            className="ml-auto flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:text-ink"
            disabled={q.isFetching}
          >
            {q.isFetching ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            обновить
          </button>
        </div>

        {q.isError && (
          <div className="panel mb-4 flex items-center gap-2 border-rust/40 p-3 text-sm text-rust">
            <TriangleAlert size={16} /> Не удалось загрузить очередь: {q.error.message}
          </div>
        )}

        {data && (
          <div className="mb-4 text-xs text-faint">
            просканировано {data.total_measurements} измерений · помечено {data.flagged}
          </div>
        )}

        {/* -- Queue ------------------------------------------------------- */}
        {q.isLoading ? (
          <div className="panel flex items-center gap-2 p-4 text-sm text-muted">
            <Loader2 size={16} className="animate-spin" /> Сканируем популяцию измерений…
          </div>
        ) : items.length === 0 ? (
          <div className="panel flex items-center gap-2 p-4 text-sm text-muted">
            <ShieldAlert size={16} /> Подозрительных значений не найдено — популяция чистая.
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((m) => (
              <MeasurementCard key={m.id} m={m} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MeasurementCard({ m }: { m: SuspectMeasurement }) {
  const worst = m.badges.some((b) => b.severity === 'hard_error');
  return (
    <div className={`panel p-4 ${worst ? 'border-rust/40' : ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="metric text-xl font-semibold text-nickel-bright">
              {fmt(m.value)}
            </span>
            <span className="text-sm text-faint">{m.unit || 'без единицы'}</span>
            {!m.indexable && (
              <span className="flex items-center gap-1 rounded bg-rust/15 px-1.5 py-0.5 text-[10px] uppercase text-rust">
                <AlertOctagon size={11} /> не индексируется
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-ink">
            {m.name || m.property_name || m.id}
          </div>
          <div className="mt-0.5 text-xs text-faint">
            {[m.property_name, m.material, m.material_class, m.domain]
              .filter(Boolean)
              .join(' · ') || '—'}
            {m.value_raw && m.value_raw !== String(m.value) && (
              <>
                {' · '}
                исходно: <code>{m.value_raw}</code>
              </>
            )}
          </div>
        </div>

        {/* Badges */}
        <div className="flex flex-shrink-0 flex-wrap gap-1.5">
          {m.badges.map((b, i) => {
            const M = FLAG_META[b.flag];
            const Icon = M?.icon ?? TriangleAlert;
            return (
              <span
                key={i}
                title={b.reason}
                className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${sevClasses(
                  b.severity,
                )}`}
              >
                <Icon size={11} /> {b.label_ru}
              </span>
            );
          })}
        </div>
      </div>

      {/* Reasons + context */}
      <div className="mt-3 space-y-1 border-t border-line/60 pt-3 text-xs text-muted">
        {m.badges.map((b, i) => (
          <div key={i} className="flex gap-1.5">
            <span className="text-faint">{FLAG_META[b.flag]?.short ?? b.flag}:</span>
            <span>{b.reason}</span>
          </div>
        ))}
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-faint">
          {m.hard_min !== null && m.hard_max !== null && (
            <span>
              физ. диапазон [{fmt(m.hard_min)}, {fmt(m.hard_max)}]
            </span>
          )}
          {m.typical_min !== null && m.typical_max !== null && (
            <span>
              типичная полоса [{fmt(m.typical_min)}, {fmt(m.typical_max)}]
            </span>
          )}
          {m.cohort_n > 0 && (
            <span>
              когорта n={m.cohort_n}, медиана {fmt(m.cohort_median)}, robust z {fmt(m.robust_z)}
            </span>
          )}
          {m.suggested_factor != null && m.corrected_value != null && (
            <span className="text-copper">
              предложение: ×{fmt(m.suggested_factor)} → {fmt(m.corrected_value)} {m.unit ?? ''}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
