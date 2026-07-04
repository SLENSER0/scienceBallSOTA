import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CalendarClock, Loader2, TriangleAlert, Boxes } from 'lucide-react';
import { api } from '../api';

// Timeline сущности (§17.11 / §5.2.4): временная шкала эволюции знания о сущности.
//
// Слева — выбор типа + сущности (реюз /graph/nodes через api.graphNodes). Справа —
// временной ряд с бэкенда `GET /api/v1/entity-timeline/{id}`: по годам — документы
// (появление сущности в корпусе), измерения/эксперименты, доказательства, и
// накопительная кривая документов. Показывает, когда сущность впервые появилась и
// как накапливалось знание о материале/технологии во времени.
//
// Рендер — чистый SVG (repo без внешних chart-зависимостей; те же токены, что и в
// CoverageDashboardView): grouped-бары по трём метрикам + линия накопления.

type TimelinePoint = {
  year: number;
  documents: number;
  mentions: number;
  measurements: number;
  evidence: number;
  cumulative_documents: number;
};

type TimelineResp = {
  entity_id: string;
  name: string;
  type: string | null;
  series: TimelinePoint[];
  summary: {
    first_seen: number | null;
    last_seen: number | null;
    span_years: number;
    years_covered: number;
    total_documents: number;
    total_mentions: number;
    total_measurements: number;
    total_evidence: number;
  };
};

const TYPES = [
  { label: 'Material', ru: 'Материалы' },
  { label: 'TechnologySolution', ru: 'Технологии' },
  { label: 'ProcessingRegime', ru: 'Режимы' },
  { label: 'Equipment', ru: 'Оборудование' },
  { label: 'Property', ru: 'Свойства' },
  { label: 'Paper', ru: 'Публикации' },
];

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

async function etFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json', ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function EntityTimelineView() {
  const [type, setType] = useState('Material');
  const [selId, setSelId] = useState<string | null>(null);

  const nodes = useQuery({ queryKey: ['tl-nodes', type], queryFn: () => api.graphNodes(type, 80) });
  const list = nodes.data?.nodes ?? [];

  useEffect(() => {
    const ns = nodes.data?.nodes ?? [];
    if (ns.length && !ns.some((n) => n.id === selId)) setSelId(ns[0].id);
  }, [nodes.data, selId]);

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[280px_1fr]">
      {/* Left: type tabs + node list */}
      <aside className="flex min-h-0 flex-col border-r border-line bg-graphite/40">
        <div className="flex flex-wrap gap-1 border-b border-line p-2">
          {TYPES.map((t) => (
            <button
              key={t.label}
              onClick={() => setType(t.label)}
              className={`rounded px-2 py-1 text-[11px] transition ${
                type === t.label ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
              }`}
            >
              {t.ru}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {nodes.isLoading ? (
            <div className="flex items-center gap-2 p-3 font-mono text-[11px] text-faint">
              <Loader2 size={13} className="animate-spin text-copper" /> загрузка…
            </div>
          ) : (
            list.map((n) => (
              <button
                key={n.id}
                onClick={() => setSelId(n.id)}
                className={`mb-1 w-full truncate rounded px-2.5 py-1.5 text-left text-xs transition ${
                  selId === n.id ? 'bg-copper/15 text-copper' : 'text-muted hover:bg-surface/60'
                }`}
                title={n.name}
              >
                {n.name || n.id}
              </button>
            ))
          )}
          {!nodes.isLoading && list.length === 0 && (
            <div className="p-3 text-center font-mono text-[11px] text-faint">нет узлов</div>
          )}
        </div>
      </aside>

      {/* Right: timeline */}
      <section className="min-h-0 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-5xl">
          <div className="eyebrow mb-1">карточка сущности · эволюция во времени</div>
          <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
            <CalendarClock size={22} className="text-copper" /> Timeline сущности
          </h1>
          <p className="mt-1 text-sm text-faint">
            Когда сущность появилась в корпусе и как накапливалось знание о ней: документы,
            измерения/эксперименты и доказательства по годам.
          </p>
          {selId ? <Timeline id={selId} /> : <Empty />}
        </div>
      </section>
    </div>
  );
}

function Empty() {
  return (
    <div className="panel mt-8 flex flex-col items-center justify-center gap-2 py-16 text-center">
      <Boxes size={26} className="text-faint" />
      <div className="font-mono text-[12px] text-faint">выберите сущность слева</div>
    </div>
  );
}

function Timeline({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ['entity-timeline', id],
    queryFn: () => etFetch<TimelineResp>(`/api/v1/entity-timeline/${encodeURIComponent(id)}`),
    staleTime: 5 * 60_000,
  });

  const series = q.data?.series ?? [];
  const s = q.data?.summary;

  const maxBar = useMemo(
    () => series.reduce((m, p) => Math.max(m, p.documents, p.measurements, p.evidence), 0),
    [series],
  );
  const maxCum = useMemo(
    () => series.reduce((m, p) => Math.max(m, p.cumulative_documents), 0),
    [series],
  );

  if (q.isLoading) {
    return (
      <div className="mt-10 flex items-center gap-2 font-mono text-sm text-faint">
        <Loader2 size={15} className="animate-spin text-copper" /> загрузка timeline…
      </div>
    );
  }
  if (q.isError) {
    return (
      <div
        className="panel mt-8 flex items-center justify-center gap-2 py-8 text-center font-mono text-[12px]"
        style={{ color: '#E5484D' }}
      >
        <TriangleAlert size={15} /> не удалось загрузить timeline сущности
      </div>
    );
  }

  return (
    <>
      <div className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11px]">
        <span className="chip text-ink" title={q.data?.entity_id}>
          {q.data?.name}
        </span>
        {q.data?.type && <span className="chip text-faint">{q.data.type}</span>}
        {s?.first_seen != null && (
          <span className="chip text-faint">
            появление {s.first_seen}
            {s.last_seen != null && s.last_seen !== s.first_seen ? `–${s.last_seen}` : ''}
          </span>
        )}
        {s && s.span_years > 0 && <span className="chip text-faint">охват {s.span_years} лет</span>}
        <span className="chip text-faint">документов {s?.total_documents ?? 0}</span>
        <span className="chip border-verified/40 text-verified">
          измерений {s?.total_measurements ?? 0}
        </span>
        <span className="chip text-faint">доказательств {s?.total_evidence ?? 0}</span>
      </div>

      <div className="panel mt-5 p-4">
        <div className="mb-3 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
          <CalendarClock size={12} className="text-copper" /> активность по годам
        </div>
        {series.length === 0 ? (
          <div className="py-12 text-center font-mono text-[11px] text-faint">
            нет датированных источников для этой сущности
          </div>
        ) : (
          <TimelineChart points={series} maxBar={maxBar} maxCum={maxCum} />
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[10px] text-faint">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-copper/70" /> документы
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-verified/70" /> измерения
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-nickel/60" /> доказательства
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-[2px] w-4 bg-copper" /> накоплено документов
          </span>
        </div>
      </div>
    </>
  );
}

// Grouped-бары (документы / измерения / доказательства) + линия накопления документов.
function TimelineChart({
  points,
  maxBar,
  maxCum,
}: {
  points: TimelinePoint[];
  maxBar: number;
  maxCum: number;
}) {
  const W = 640;
  const H = 230;
  const padL = 34;
  const padR = 34;
  const padT = 12;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const n = points.length;
  const slot = plotW / n;
  const groupW = Math.min(42, slot * 0.7);
  const barW = groupW / 3;

  const yBar = (v: number) => padT + plotH - (maxBar ? (v / maxBar) * plotH : 0);
  const yCum = (v: number) => padT + plotH - (maxCum ? (v / maxCum) * plotH : 0);

  const cumPts = points
    .map((p, i) => `${padL + slot * i + slot / 2},${yCum(p.cumulative_documents)}`)
    .join(' ');

  // Разреженные подписи лет, чтобы не наезжали при большом числе лет.
  const step = Math.max(1, Math.ceil(n / 14));

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 340 }}>
        {/* Горизонтальные направляющие (0 / 50 / 100 % от maxBar) */}
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line
              x1={padL}
              x2={W - padR}
              y1={padT + plotH - r * plotH}
              y2={padT + plotH - r * plotH}
              className="stroke-line/50"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text
              x={padL - 6}
              y={padT + plotH - r * plotH + 3}
              textAnchor="end"
              className="fill-faint font-mono"
              fontSize={8}
            >
              {Math.round(r * maxBar)}
            </text>
          </g>
        ))}

        {points.map((p, i) => {
          const gx = padL + slot * i + (slot - groupW) / 2;
          const bars = [
            { v: p.documents, cls: 'fill-copper/70', lbl: 'документов' },
            { v: p.measurements, cls: 'fill-verified/70', lbl: 'измерений' },
            { v: p.evidence, cls: 'fill-nickel/60', lbl: 'доказательств' },
          ];
          return (
            <g key={p.year}>
              {bars.map((b, bi) => {
                const top = yBar(b.v);
                return (
                  <rect
                    key={bi}
                    x={gx + bi * barW}
                    y={top}
                    width={Math.max(1.5, barW - 1)}
                    height={padT + plotH - top}
                    className={b.cls}
                  >
                    <title>{`${p.year}: ${b.v} ${b.lbl}`}</title>
                  </rect>
                );
              })}
              {i % step === 0 && (
                <text
                  x={padL + slot * i + slot / 2}
                  y={H - 8}
                  textAnchor="middle"
                  className="fill-faint font-mono"
                  fontSize={8}
                >
                  {p.year}
                </text>
              )}
            </g>
          );
        })}

        {/* Накопительная кривая документов (правая ось) */}
        {n > 1 && (
          <polyline
            points={cumPts}
            fill="none"
            className="stroke-copper"
            strokeWidth={1.5}
            strokeLinejoin="round"
          />
        )}
        {points.map((p, i) => (
          <circle
            key={`c-${p.year}`}
            cx={padL + slot * i + slot / 2}
            cy={yCum(p.cumulative_documents)}
            r={2.2}
            className="fill-copper"
          >
            <title>{`${p.year}: накоплено ${p.cumulative_documents} документов`}</title>
          </circle>
        ))}
        {/* правая ось — макс накопления */}
        <text x={W - padR + 4} y={padT + 4} className="fill-faint font-mono" fontSize={8}>
          {maxCum}
        </text>
      </svg>
    </div>
  );
}
