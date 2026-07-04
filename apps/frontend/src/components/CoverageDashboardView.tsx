import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LayoutDashboard, Loader2, TriangleAlert, CircleDashed, Building2 } from 'lucide-react';

// Дашборд покрытия: динамика во времени + пробелы по лабам/командам (§15.5 / §5.2.7).
//
// Управленческий срез панели пробелов. Бэкенд `GET /api/v1/coverage/dashboard`
// отдаёт два уже готовых ряда (переиспользует
// `kg_retrievers.coverage_matrix.build_coverage_timeline` и
// `aggregate_gaps_by_owner`):
//   • timeline — по годам: статьи, измерения-доказательства, пробелы и
//     производный `coverage_ratio` (доля покрытия);
//   • by_owner — открытые пробелы, сгруппированные по владельцу (лаборатория /
//     домен), отсортированные «худшие сверху».
//
// Здесь это визуализируется: слева — временной ряд покрытия (столбики измерений +
// пробелов и линия доли покрытия), справа — ранжированный список «у кого не хватает
// метаданных». Рендер на чистом SVG/CSS (без внешних chart-зависимостей).

type TimelinePoint = {
  year: number;
  paper_count: number;
  measurement_count: number;
  gap_count: number;
  coverage_ratio: number;
};

type OwnerRow = {
  owner: string;
  lab_id: string | null;
  lab_name: string | null;
  gap_count: number;
  gap_ids: string[];
};

type DashboardResp = {
  timeline: TimelinePoint[];
  by_owner: OwnerRow[];
  summary: {
    years: number;
    papers: number;
    measurements: number;
    gaps_dated: number;
    gaps_total: number;
    owners: number;
    unassigned_gaps: number;
    shown_owners: number;
  };
};

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

async function cdFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

const ownerLabel = (o: OwnerRow) =>
  o.lab_name ?? (o.owner === 'unassigned' ? 'Без привязки (нет лаборатории/команды)' : o.owner);

export function CoverageDashboardView() {
  const q = useQuery({
    queryKey: ['coverage-dashboard'],
    queryFn: () => cdFetch<DashboardResp>('/api/v1/coverage/dashboard'),
    staleTime: 5 * 60_000,
  });

  const timeline = q.data?.timeline ?? [];
  const byOwner = q.data?.by_owner ?? [];
  const summary = q.data?.summary;

  // Верхняя граница столбиков (measurements + gaps по году) для нормировки высоты.
  const maxStack = useMemo(
    () => timeline.reduce((m, p) => Math.max(m, p.measurement_count + p.gap_count), 0),
    [timeline],
  );
  const maxGap = useMemo(() => byOwner.reduce((m, o) => Math.max(m, o.gap_count), 0), [byOwner]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">панель пробелов · управленческий срез</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <LayoutDashboard size={22} className="text-copper" /> Дашборд покрытия
        </h1>
        <p className="mt-1 text-sm text-faint">
          Динамика покрытия во времени и распределение пробелов по лабораториям /
          командам. Столбики — измерения и пробелы по годам, линия — доля покрытия;
          справа — у кого не хватает метаданных.
        </p>

        {q.isLoading ? (
          <div className="mt-10 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> загрузка дашборда покрытия…
          </div>
        ) : q.isError ? (
          <div
            className="panel mt-8 flex items-center justify-center gap-2 py-8 text-center font-mono text-[12px]"
            style={{ color: '#E5484D' }}
          >
            <TriangleAlert size={15} /> не удалось загрузить /coverage/dashboard
          </div>
        ) : (
          <>
            {summary && (
              <div className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11px]">
                <span className="chip text-faint">лет {summary.years}</span>
                <span className="chip text-faint">статей {summary.papers}</span>
                <span className="chip border-verified/40 text-verified">
                  измерений {summary.measurements}
                </span>
                <span className="chip border-gap/40 text-gap">пробелов {summary.gaps_total}</span>
                <span className="chip text-faint">лаб/доменов {summary.owners}</span>
                {summary.unassigned_gaps > 0 && (
                  <span className="chip border-gap/40 text-gap">
                    без привязки {summary.unassigned_gaps}
                  </span>
                )}
              </div>
            )}

            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              {/* Панель 1: динамика покрытия во времени */}
              <div className="panel p-4">
                <div className="mb-3 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
                  <LayoutDashboard size={12} className="text-copper" /> динамика покрытия по годам
                </div>
                {timeline.length === 0 ? (
                  <div className="py-10 text-center font-mono text-[11px] text-faint">
                    нет статей с проставленным годом
                  </div>
                ) : (
                  <TimelineChart points={timeline} maxStack={maxStack} />
                )}
                <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[10px] text-faint">
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-verified" /> измерения
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-gap" /> пробелы
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-[2px] w-4 bg-copper" /> доля покрытия
                  </span>
                </div>
              </div>

              {/* Панель 2: у кого не хватает метаданных */}
              <div className="panel p-4">
                <div className="mb-3 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
                  <Building2 size={12} className="text-copper" /> пробелы по лабам / командам
                </div>
                {byOwner.length === 0 ? (
                  <div className="py-10 text-center font-mono text-[11px] text-faint">
                    открытых пробелов не найдено
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {byOwner.map((o) => (
                      <li key={`${o.owner}|${o.lab_id ?? ''}`} className="text-[12px]">
                        <div className="mb-1 flex items-center gap-2">
                          <span className="truncate text-ink" title={o.lab_id ?? o.owner}>
                            {ownerLabel(o)}
                          </span>
                          <span className="ml-auto flex items-center gap-1 font-mono text-[11px] text-gap">
                            <CircleDashed size={12} /> {o.gap_count}
                          </span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-line/40">
                          <div
                            className="h-full rounded-full bg-gap/70"
                            style={{ width: `${maxGap ? (o.gap_count / maxGap) * 100 : 0}%` }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Столбчатый ряд (measurements + gaps, стек) с наложенной линией доли покрытия.
function TimelineChart({ points, maxStack }: { points: TimelinePoint[]; maxStack: number }) {
  const W = 560;
  const H = 200;
  const padL = 34;
  const padR = 12;
  const padT = 10;
  const padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const n = points.length;
  const slot = plotW / n;
  const barW = Math.min(30, slot * 0.6);

  const yBar = (v: number) => padT + plotH - (maxStack ? (v / maxStack) * plotH : 0);
  const yRatio = (r: number) => padT + plotH - r * plotH; // ratio уже 0..1

  const linePts = points
    .map((p, i) => `${padL + slot * i + slot / 2},${yRatio(p.coverage_ratio)}`)
    .join(' ');

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 320 }}>
        {/* Горизонтальные направляющие 0 / 50 / 100 % покрытия */}
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line
              x1={padL}
              x2={W - padR}
              y1={yRatio(r)}
              y2={yRatio(r)}
              className="stroke-line/50"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text
              x={padL - 6}
              y={yRatio(r) + 3}
              textAnchor="end"
              className="fill-faint font-mono"
              fontSize={8}
            >
              {Math.round(r * 100)}%
            </text>
          </g>
        ))}

        {points.map((p, i) => {
          const cx = padL + slot * i;
          const x = cx + (slot - barW) / 2;
          const stack = p.measurement_count + p.gap_count;
          const measTop = yBar(stack);
          const gapTop = yBar(p.gap_count);
          return (
            <g key={p.year}>
              {/* пробелы (низ стека) */}
              <rect
                x={x}
                y={gapTop}
                width={barW}
                height={padT + plotH - gapTop}
                className="fill-gap/60"
              >
                <title>{`${p.year}: пробелов ${p.gap_count}`}</title>
              </rect>
              {/* измерения (верх стека) */}
              <rect
                x={x}
                y={measTop}
                width={barW}
                height={gapTop - measTop}
                className="fill-verified/70"
              >
                <title>{`${p.year}: измерений ${p.measurement_count}, статей ${p.paper_count}`}</title>
              </rect>
              <text
                x={cx + slot / 2}
                y={H - 8}
                textAnchor="middle"
                className="fill-faint font-mono"
                fontSize={8}
              >
                {p.year}
              </text>
            </g>
          );
        })}

        {/* линия доли покрытия */}
        {n > 1 && (
          <polyline
            points={linePts}
            fill="none"
            className="stroke-copper"
            strokeWidth={1.5}
            strokeLinejoin="round"
          />
        )}
        {points.map((p, i) => (
          <circle
            key={`d-${p.year}`}
            cx={padL + slot * i + slot / 2}
            cy={yRatio(p.coverage_ratio)}
            r={2.5}
            className="fill-copper"
          >
            <title>{`${p.year}: покрытие ${(p.coverage_ratio * 100).toFixed(1)}%`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}
