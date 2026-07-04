import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  FlaskConical,
  HelpCircle,
  Loader2,
  Ruler,
  ScanSearch,
  ShieldQuestion,
} from 'lucide-react';

// §7.6 — Review-очередь неоднозначных / отсутствующих единиц + gap missing_unit.
//
// Движок НЕ угадывает базис: «2.5 %» в контексте состава не превращается молча в
// wt% или at% — вместо этого заводится review-таск с вариантами (wt% / at% / vol%),
// а «320» без единицы падает в gap missing_unit (§11.1) и попадает в Карту пробелов.
// Этот экран показывает обе честные развязки поверх живого графа (Neo4j :8000):
//   GET  /api/v1/unit-review/queue     — очередь + матрица пробелов (kind × domain)
//   POST /api/v1/unit-review/explain   — «проиграть» вердикт для произвольного значения
// Бэкенд переиспользует уже готовые детекторы (unit_ambiguous / unit_problems),
// фронт только рендерит. Без внешних chart-зависимостей — чистый CSS-grid.

type Kind = 'ambiguous_unit' | 'missing_unit';

interface UnitReviewTask {
  id: string;
  kind: Kind;
  kind_ru: string;
  name: string | null;
  property_name: string | null;
  property_id: string | null;
  material: string | null;
  domain: string | null;
  value: number | null;
  value_raw: string | null;
  unit: string | null;
  candidates: string[];
  reason: string;
  gap_type: string;
  doc_id: string | null;
  page: number | null;
}

interface QueueResponse {
  total_measurements: number;
  flagged: number;
  counts: Record<string, number>;
  gap_matrix: Record<string, Record<string, number>>;
  tasks: UnitReviewTask[];
}

interface ExplainResponse {
  kind: Kind | null;
  kind_ru: string | null;
  unit_ambiguous: boolean;
  unit_missing: boolean;
  candidates: string[];
  reason: string;
  is_missing_unit_gap: boolean;
}

const KIND_META: Record<Kind, { label: string; icon: typeof AlertTriangle; color: string }> = {
  ambiguous_unit: { label: 'неоднозначная единица', icon: ShieldQuestion, color: '#c98a2b' },
  missing_unit: { label: 'нет единицы', icon: AlertTriangle, color: '#b04a3a' },
};

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  electrometallurgy: 'Электромет',
  mineral_processing: 'Обогащение',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  environment: 'Экология',
  '?': 'н/д',
};
const ruDomain = (d: string) => DOMAIN_RU[d] ?? d;

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

async function fetchQueue(): Promise<QueueResponse> {
  const res = await fetch('/api/v1/unit-review/queue?limit=5000', {
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function postExplain(body: {
  value_raw: string;
  property_context: string;
}): Promise<ExplainResponse> {
  const res = await fetch('/api/v1/unit-review/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function UnitReviewView() {
  const [kind, setKind] = useState<Kind | null>(null);
  const q = useQuery({ queryKey: ['unit-review-queue'], queryFn: fetchQueue });

  const tasks = useMemo(() => {
    const all = q.data?.tasks ?? [];
    return kind ? all.filter((t) => t.kind === kind) : all;
  }, [q.data, kind]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">нормализация единиц · честный review (§7.6)</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Ruler size={22} className="text-copper" /> Единицы на ревью
        </h1>
        <p className="mt-1 text-sm text-faint">
          Движок не угадывает базис молча: «%» без wt/at/vol в контексте состава уходит в
          review-таск с вариантами, а значение без единицы — в gap <code>missing_unit</code> и в
          Карту пробелов. Ниже — обе развязки поверх живого графа.
        </p>

        <ExplainPanel />

        {q.isLoading && (
          <div className="mt-8 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> сканирую измерения
          </div>
        )}
        {q.isError && (
          <div className="panel mt-6 border-copper/40 p-4 text-sm text-copper">
            ошибка загрузки очереди: {(q.error as Error).message}
          </div>
        )}

        {q.data && (
          <>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <KindChip
                active={kind === null}
                label="всё"
                count={q.data.flagged}
                onClick={() => setKind(null)}
                color="#8a8a8a"
              />
              {(['missing_unit', 'ambiguous_unit'] as Kind[]).map((k) => (
                <KindChip
                  key={k}
                  active={kind === k}
                  label={KIND_META[k].label}
                  count={q.data!.counts[k] ?? 0}
                  onClick={() => setKind(kind === k ? null : k)}
                  color={KIND_META[k].color}
                />
              ))}
              <span className="ml-auto font-mono text-[11px] text-faint">
                {q.data.flagged} из {q.data.total_measurements} измерений
              </span>
            </div>

            <GapMatrix matrix={q.data.gap_matrix} />

            <div className="mt-5 space-y-2.5">
              {tasks.length === 0 ? (
                <div className="panel py-10 text-center font-mono text-[11px] text-faint">
                  нет задач для этого фильтра
                </div>
              ) : (
                tasks.map((t) => <TaskCard key={t.id} t={t} />)
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function KindChip({
  active,
  label,
  count,
  onClick,
  color,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
  color: string;
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors"
      style={{
        borderColor: active ? color : 'var(--line, #333)',
        background: active ? `${color}22` : 'transparent',
      }}
    >
      <span className={active ? 'font-medium' : 'text-faint'}>{label}</span>
      <span className="metric text-[10px] opacity-80">{count}</span>
    </button>
  );
}

function GapMatrix({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const kinds = Object.keys(matrix);
  const domains = useMemo(() => {
    const set = new Set<string>();
    for (const row of Object.values(matrix)) for (const d of Object.keys(row)) set.add(d);
    return [...set].sort();
  }, [matrix]);
  const max = useMemo(() => {
    let m = 0;
    for (const row of Object.values(matrix)) for (const v of Object.values(row)) m = Math.max(m, v);
    return m;
  }, [matrix]);

  if (kinds.length === 0) return null;

  return (
    <div className="panel mt-5 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] text-faint">
        <ScanSearch size={13} className="text-copper" /> Карта пробелов · тип × домен
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left font-normal text-faint">тип</th>
              {domains.map((d) => (
                <th key={d} className="px-2 py-1 text-center font-normal text-faint">
                  {ruDomain(d)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {kinds.map((k) => (
              <tr key={k}>
                <td className="whitespace-nowrap px-2 py-1 font-mono text-ink">{k}</td>
                {domains.map((d) => {
                  const c = matrix[k]?.[d] ?? 0;
                  const t = max <= 0 ? 0 : Math.pow(c / max, 0.6);
                  return (
                    <td
                      key={d}
                      className="px-2 py-1 text-center"
                      style={{
                        background: c > 0 ? `rgba(184, 115, 51, ${(0.12 + t * 0.8).toFixed(3)})` : undefined,
                        color: t > 0.55 ? '#141414' : undefined,
                      }}
                    >
                      {c > 0 ? c : '·'}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TaskCard({ t }: { t: UnitReviewTask }) {
  const meta = KIND_META[t.kind];
  const Icon = meta.icon;
  return (
    <div className="panel p-4" style={{ borderColor: `${meta.color}55` }}>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{ background: `${meta.color}22`, color: meta.color }}
        >
          <Icon size={12} /> {t.kind_ru}
        </span>
        {t.material && (
          <span className="text-sm text-ink/90">
            {t.material} <span className="text-faint">×</span>{' '}
          </span>
        )}
        {t.property_name && (
          <span className="font-mono text-[13px] text-ink">{t.property_name}</span>
        )}
        {t.domain && <span className="chip text-[10px] text-faint">{ruDomain(t.domain)}</span>}
      </div>

      <div className="mt-2 flex items-center gap-2 font-mono text-[13px]">
        <FlaskConical size={13} className="text-faint" />
        <span className="text-ink">
          {t.value_raw ?? (t.value != null ? String(t.value) : '—')}
        </span>
        {t.unit && <span className="text-copper">{t.unit}</span>}
      </div>

      <p className="mt-2 text-[12px] leading-snug text-faint">{t.reason}</p>

      {t.candidates.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-faint">варианты базиса:</span>
          {t.candidates.map((c) => (
            <span
              key={c}
              className="rounded-md border border-line px-2 py-0.5 font-mono text-[11px] text-ink"
            >
              {c}
            </span>
          ))}
        </div>
      )}

      {(t.doc_id || t.page != null) && (
        <div className="mt-2 font-mono text-[10px] text-faint">
          источник: {t.doc_id ?? '—'}
          {t.page != null ? ` · с. ${t.page}` : ''}
        </div>
      )}
    </div>
  );
}

function ExplainPanel() {
  const [value, setValue] = useState('2.5 %');
  const [ctx, setCtx] = useState('composition');
  const m = useMutation({
    mutationFn: () => postExplain({ value_raw: value, property_context: ctx }),
  });

  return (
    <div className="panel mt-5 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] text-faint">
        <HelpCircle size={13} className="text-copper" /> Проиграть вердикт нормализации
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-faint">значение</span>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-40 rounded-md border border-line bg-panel px-2 py-1 font-mono text-[13px] text-ink"
            placeholder="2.5 % / 320"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-faint">контекст свойства</span>
          <input
            value={ctx}
            onChange={(e) => setCtx(e.target.value)}
            className="w-48 rounded-md border border-line bg-panel px-2 py-1 font-mono text-[13px] text-ink"
            placeholder="composition / tensile_strength"
          />
        </label>
        <button
          onClick={() => m.mutate()}
          className="rounded-md border border-copper/60 bg-copper/15 px-3 py-1.5 text-[12px] text-copper hover:bg-copper/25"
        >
          проверить
        </button>
      </div>

      {m.isPending && (
        <div className="mt-3 flex items-center gap-2 font-mono text-[11px] text-faint">
          <Loader2 size={13} className="animate-spin text-copper" /> считаю
        </div>
      )}
      {m.isError && (
        <div className="mt-3 text-[12px] text-copper">ошибка: {(m.error as Error).message}</div>
      )}
      {m.data && (
        <div className="mt-3 rounded-md border border-line p-3 text-[12px]">
          {m.data.kind ? (
            <div className="flex items-center gap-2">
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
                style={{
                  background: `${KIND_META[m.data.kind].color}22`,
                  color: KIND_META[m.data.kind].color,
                }}
              >
                {m.data.kind_ru}
              </span>
              {m.data.is_missing_unit_gap && (
                <span className="chip text-[10px] text-faint">→ gap missing_unit</span>
              )}
            </div>
          ) : (
            <span className="text-nickel">единица однозначна — review не требуется</span>
          )}
          <p className="mt-2 text-faint">{m.data.reason}</p>
          {m.data.candidates.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-faint">варианты (не выбираем молча):</span>
              {m.data.candidates.map((c) => (
                <span
                  key={c}
                  className="rounded-md border border-line px-2 py-0.5 font-mono text-[11px] text-ink"
                >
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
