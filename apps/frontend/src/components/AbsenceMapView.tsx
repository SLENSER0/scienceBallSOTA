import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowDownWideNarrow,
  BadgeCheck,
  FlaskConical,
  HelpCircle,
  Info,
  Loader2,
  Map as MapIcon,
  SearchX,
} from 'lucide-react';

// «Карта неизвестного» (§25.14) — surfaces the absence layer's per-cell verdict so a
// gap is no longer a flat hole. Each (material × property) cell the classifier could
// not confirm is shown with: its verdict (genuine_gap / possible_miss / retracted /
// abstain), the «риск пропуска извлечения N%» (P(extractor missed)), a калибровано/
// эвристика badge, and a short RU rationale (MENTIONS, recall prior, retraction state).
// Data: GET /api/v1/gaps/absence (read-only; reuses absence_signals + absence_rationale).

type Verdict = 'genuine_gap' | 'possible_miss' | 'retracted' | 'abstain' | 'present' | 'covered';

interface AbsenceRationale {
  verdict: string;
  headline: string;
  factors: string[];
  calibrated: boolean;
}

interface AbsenceGap {
  gap_id: string;
  material_id: string;
  material_name: string;
  property_name: string;
  domain: string | null;
  absence_verdict: Verdict;
  verdict_ru: string;
  p_truly_absent: number;
  p_extractor_missed: number;
  extractor_miss_risk_pct: number;
  is_genuine_gap: boolean;
  non_white_gap: boolean;
  absence_meta: { calibrated: boolean; method: string; recall_prior: number | null };
  signals: {
    active_observations: number;
    retracted_observations: number;
    mentioned_without_observation: boolean;
  };
  rationale: AbsenceRationale;
}

interface AbsenceResponse {
  count: number;
  by_verdict: Record<string, number>;
  verdict_labels: Record<string, string>;
  calibrated: boolean;
  gaps: AbsenceGap[];
}

// The absence_confidence glossary article (§25.14 «глоссарий absence confidence»).
const ABSENCE_CONFIDENCE_GLOSSARY =
  'Уверенность отсутствия (absence confidence): вероятность того, что пробел — настоящий ' +
  '(данных действительно нет), а не пропуск извлечения. Мы различаем «реальный пробел» ' +
  '(genuine_gap), «возможно пропуск извлечения» (possible_miss — сущность упоминается, но ' +
  'значение не извлечено), «ретрагировано» (retracted — источник отозван) и «неопределённо» ' +
  '(abstain). Риск пропуска извлечения = P(extractor missed). Статус «калибровано» означает, ' +
  'что порог откалиброван по эталонной выборке; «эвристика» — по умолчанию.';

const VERDICT_STYLE: Record<
  string,
  { ru: string; color: string; bg: string; border: string; icon: typeof SearchX }
> = {
  genuine_gap: {
    ru: 'реальный пробел',
    color: '#E5484D',
    bg: 'rgba(229,72,77,0.12)',
    border: 'rgba(229,72,77,0.4)',
    icon: SearchX,
  },
  possible_miss: {
    ru: 'возможно пропуск извлечения',
    color: '#E0A23C',
    bg: 'rgba(224,162,60,0.14)',
    border: 'rgba(224,162,60,0.45)',
    icon: AlertTriangle,
  },
  retracted: {
    ru: 'ретрагировано',
    color: '#8B7BD8',
    bg: 'rgba(139,123,216,0.14)',
    border: 'rgba(139,123,216,0.4)',
    icon: FlaskConical,
  },
  abstain: {
    ru: 'неопределённо',
    color: '#8FA3B0',
    bg: 'rgba(143,163,176,0.12)',
    border: 'rgba(143,163,176,0.35)',
    icon: HelpCircle,
  },
};

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  environment: 'Экология',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электромет',
};

type SortKey = 'p_extractor_missed' | 'p_truly_absent';

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

async function fetchAbsence(): Promise<AbsenceResponse> {
  const res = await fetch('/api/v1/gaps/absence?limit=200', {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<AbsenceResponse>;
}

function InfoDot({ text }: { text: string }) {
  return (
    <span className="group relative ml-1 inline-flex cursor-help align-middle">
      <Info size={13} className="text-faint hover:text-copper" />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-5 z-20 w-72 -translate-x-1/2 rounded-md border border-line bg-panel px-3 py-2 text-[11px] leading-snug text-ink opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

function CalibrationBadge({ calibrated }: { calibrated: boolean }) {
  return calibrated ? (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={{ color: '#3DA35D', background: 'rgba(61,163,93,0.12)' }}
    >
      <BadgeCheck size={11} /> калибровано
    </span>
  ) : (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={{ color: '#8FA3B0', background: 'rgba(143,163,176,0.12)' }}
    >
      <FlaskConical size={11} /> эвристика
    </span>
  );
}

export function AbsenceMapView() {
  const q = useQuery({
    queryKey: ['absence-map'],
    queryFn: fetchAbsence,
    staleTime: 2 * 60_000,
  });
  const [filter, setFilter] = useState<Verdict | 'all'>('all');
  const [sortKey, setSortKey] = useState<SortKey>('p_extractor_missed');

  const gaps = useMemo(() => {
    const list = (q.data?.gaps ?? []).filter(
      (g) => filter === 'all' || g.absence_verdict === filter,
    );
    return [...list].sort((a, b) => b[sortKey] - a[sortKey]);
  }, [q.data, filter, sortKey]);

  const byVerdict = q.data?.by_verdict ?? {};
  const total = q.data?.count ?? 0;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">карта неизвестного · вердикт отсутствия</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <MapIcon size={22} className="text-copper" /> Карта неизвестного
          <InfoDot text={ABSENCE_CONFIDENCE_GLOSSARY} />
        </h1>
        <p className="mt-1 text-sm text-faint">
          Не плоский список дыр, а вердикт по каждому пробелу: настоящий пробел, вероятный
          пропуск извлечения, ретракция или неопределённость — с риском пропуска извлечения и
          отметкой калибровано/эвристика.
        </p>

        {/* Filter chips + verdict counts (§25.14 фильтр по absence_verdict). */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <FilterChip
            active={filter === 'all'}
            onClick={() => setFilter('all')}
            label="Все"
            count={total}
            color="#C8823C"
          />
          {(['genuine_gap', 'possible_miss', 'retracted', 'abstain'] as Verdict[]).map((v) => (
            <FilterChip
              key={v}
              active={filter === v}
              onClick={() => setFilter(v)}
              label={VERDICT_STYLE[v].ru}
              count={byVerdict[v] ?? 0}
              color={VERDICT_STYLE[v].color}
            />
          ))}
          <button
            type="button"
            onClick={() =>
              setSortKey((k) =>
                k === 'p_extractor_missed' ? 'p_truly_absent' : 'p_extractor_missed',
              )
            }
            className="ml-auto inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11px] text-faint hover:text-nickel"
            title="Сортировка"
          >
            <ArrowDownWideNarrow size={12} />
            {sortKey === 'p_extractor_missed' ? 'риск пропуска ↓' : 'реальное отсутствие ↓'}
          </button>
        </div>

        {q.isLoading ? (
          <div className="mt-8 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> классификатор оценивает
            ячейки…
          </div>
        ) : q.isError ? (
          <div className="panel mt-6 border-copper/40 p-4 text-sm text-copper">
            Не удалось загрузить карту отсутствия.
          </div>
        ) : (
          <div className="mt-5 space-y-2.5">
            {gaps.map((g) => (
              <AbsenceCard key={g.gap_id} g={g} />
            ))}
            {gaps.length === 0 && (
              <div className="panel py-10 text-center font-mono text-[11px] text-faint">
                нет ячеек с выбранным вердиктом
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  count,
  color,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  color: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors"
      style={{
        borderColor: active ? color : 'var(--line, rgba(143,163,176,0.3))',
        background: active ? `${color}22` : 'transparent',
        color: active ? color : undefined,
      }}
    >
      <span className={active ? 'font-medium' : 'text-faint'}>{label}</span>
      <span className="metric text-[10px] opacity-80">{count}</span>
    </button>
  );
}

function AbsenceCard({ g }: { g: AbsenceGap }) {
  const style = VERDICT_STYLE[g.absence_verdict] ?? VERDICT_STYLE.abstain;
  const Icon = style.icon;
  // §25.14: possible_miss / retracted / abstain must NOT read as an ordinary white gap —
  // give them a colored left rail + tinted surface so they never blend into a plain hole.
  const warn = g.non_white_gap;

  return (
    <div
      className="panel p-4"
      style={{
        borderLeft: `3px solid ${style.color}`,
        background: warn ? style.bg : undefined,
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{ color: style.color, background: style.bg, border: `1px solid ${style.border}` }}
        >
          <Icon size={12} /> {g.verdict_ru}
        </span>
        <span className="text-sm text-ink/90">
          {g.material_name} <span className="text-faint">×</span>{' '}
          <span className="font-mono text-[13px]">{g.property_name}</span>
        </span>
        {g.domain && (
          <span className="chip text-[10px] text-faint">{DOMAIN_RU[g.domain] ?? g.domain}</span>
        )}
        <CalibrationBadge calibrated={g.absence_meta.calibrated} />
      </div>

      {/* «риск пропуска извлечения N%» с полосой. */}
      <div className="mt-3 flex items-center gap-3">
        <div className="flex-1">
          <div className="mb-1 flex items-center justify-between text-[10px] text-faint">
            <span>риск пропуска извлечения</span>
            <span className="metric" style={{ color: style.color }}>
              {g.extractor_miss_risk_pct}%
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-line/40">
            <div
              className="h-full rounded-full"
              style={{ width: `${g.extractor_miss_risk_pct}%`, background: style.color }}
            />
          </div>
        </div>
        <div className="text-right text-[10px] text-faint">
          <div>
            реальное отсутствие{' '}
            <span className="metric text-ink/80">{Math.round(g.p_truly_absent * 100)}%</span>
          </div>
        </div>
      </div>

      {/* Rationale: headline + factors (MENTIONS / recall / retraction / порог). */}
      <div className="mt-3 border-t border-line/50 pt-2.5">
        <div className="text-[12px] font-medium text-ink/85">{g.rationale.headline}</div>
        <ul className="mt-1 space-y-0.5">
          {g.rationale.factors.map((f, i) => (
            <li key={i} className="flex gap-1.5 text-[11px] text-faint">
              <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-faint/60" />
              {f}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
