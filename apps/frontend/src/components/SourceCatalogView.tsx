import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Database,
  Loader2,
  TriangleAlert,
  Search,
  User,
  FlaskConical,
  Lock,
  Clock,
  FileText,
  GitBranch,
  ExternalLink,
  CircleOff,
} from 'lucide-react';

// Source Catalog в Admin с интерактивным lineage-графом (§10.7 / §5.2.8).
//
// Governance-каталог источников: таблица с фильтрами (поиск, лаборатория, владелец,
// доступ, свежесть), карточка выбранного источника (owner/lab/версия/доступ/свежесть/
// счётчики evidence и прогонов) и наглядный lineage-граф RAW→Neo4j/Qdrant/OpenSearch.
//
// Бэкенд `GET /api/v1/admin/catalog/*` собирает каталог из живого графа (Document/Paper
// сервера Neo4j), переиспользуя готовые чистые модули каталога (source_catalog_card,
// catalog_source_query, source_freshness) и рисуемый lineage-подграф из канонического
// §9.1-пайплайна (pipeline_lineage_spec + lineage_subgraph). При недоступном каталоге
// приходит `available: false` — UI показывает graceful-fallback вместо ошибки.
//
// Lineage рисуется чистым SVG в hierarchical (layered) раскладке: колонка = depth от
// источника, ряд — узел слоя (эквивалент dagre/ELK left→right, без внешних зависимостей).

type CatalogCard = {
  source_id: string;
  name: string;
  owner: string;
  lab: string;
  access: string;
  version: number;
  freshness: string;
  evidence_count: number;
  run_count: number;
  last_ingest: string;
  age_days: number | null;
  label: string;
};

type CatalogPage = {
  items: CatalogCard[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  available: boolean;
  source_count: number;
};

type Facets = {
  available: boolean;
  labs: string[];
  owners: string[];
  access: string[];
  by_lab: Record<string, number>;
  total: number;
};

type LineageNode = {
  id: string;
  role: 'upstream' | 'focus' | 'downstream';
  depth: number;
  kind: 'raw' | 'pipeline' | 'store';
  label: string;
  urn?: string;
  platform?: string;
  deeplink?: string;
};

type LineagePayload = {
  focus: string;
  name: string;
  nodes: LineageNode[];
  edges: [string, string][];
  available: boolean;
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

async function scFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// --- Freshness presentation -----------------------------------------------
const FRESH_META: Record<string, { ru: string; rgb: string }> = {
  fresh: { ru: 'свежий', rgb: '70, 167, 88' },
  aging: { ru: 'стареет', rgb: '184, 115, 51' },
  stale: { ru: 'устарел', rgb: '226, 84, 61' },
  unknown: { ru: 'неизвестно', rgb: '138, 148, 158' },
};

function freshMeta(level: string) {
  return FRESH_META[level] ?? FRESH_META.unknown;
}

// --- Lineage layout (SVG user units; hierarchical / layered, dagre-style) ---
const KIND_RGB: Record<LineageNode['kind'], string> = {
  raw: '184, 115, 51', // copper — источник (RAW)
  pipeline: '138, 148, 158', // steel — шаги пайплайна
  store: '70, 167, 88', // green — serving-store (Neo4j/Qdrant/OpenSearch)
};

const COL_W = 168;
const NODE_W = 138;
const NODE_H = 40;
const ROW_GAP = 16;
const X_PAD = 20;
const Y_PAD = 24;

type PlacedLineageNode = LineageNode & { x: number; y: number };

function buildLineageLayout(data: LineagePayload | undefined) {
  if (!data || data.nodes.length === 0) return null;
  // Group by depth → columns (left→right). Rows within a column stacked by id.
  const byDepth = new Map<number, LineageNode[]>();
  let maxDepth = 0;
  for (const n of data.nodes) {
    maxDepth = Math.max(maxDepth, n.depth);
    const arr = byDepth.get(n.depth) ?? [];
    arr.push(n);
    byDepth.set(n.depth, arr);
  }
  let maxRows = 0;
  const placed = new Map<string, PlacedLineageNode>();
  for (let d = 0; d <= maxDepth; d++) {
    const col = (byDepth.get(d) ?? []).slice().sort((a, b) => a.id.localeCompare(b.id));
    maxRows = Math.max(maxRows, col.length);
    col.forEach((n, i) => {
      placed.set(n.id, {
        ...n,
        x: X_PAD + d * COL_W,
        y: Y_PAD + i * (NODE_H + ROW_GAP),
      });
    });
  }
  const width = X_PAD * 2 + (maxDepth + 1) * COL_W - (COL_W - NODE_W);
  const height = Y_PAD * 2 + Math.max(1, maxRows) * (NODE_H + ROW_GAP) - ROW_GAP;
  const edges = data.edges
    .map(([s, t]) => ({ s: placed.get(s), t: placed.get(t) }))
    .filter((e): e is { s: PlacedLineageNode; t: PlacedLineageNode } => !!e.s && !!e.t);
  return { nodes: [...placed.values()], edges, width, height };
}

function edgePath(
  s: { x: number; y: number },
  t: { x: number; y: number },
): string {
  const x0 = s.x + NODE_W;
  const y0 = s.y + NODE_H / 2;
  const x1 = t.x;
  const y1 = t.y + NODE_H / 2;
  const xm = (x0 + x1) / 2;
  return `M${x0},${y0} C${xm},${y0} ${xm},${y1} ${x1},${y1}`;
}

// --- Small presentational helpers -----------------------------------------
function CardField({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 text-faint">{icon}</span>
      <div>
        <div className="text-[10px] uppercase tracking-wide text-faint">{label}</div>
        <div className="font-mono text-[12px] text-ink">{value}</div>
      </div>
    </div>
  );
}

export function SourceCatalogView() {
  const [q, setQ] = useState('');
  const [lab, setLab] = useState('');
  const [owner, setOwner] = useState('');
  const [access, setAccess] = useState('');
  const [freshness, setFreshness] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  const facetsQ = useQuery({
    queryKey: ['catalog-facets'],
    queryFn: () => scFetch<Facets>('/api/v1/admin/catalog/facets'),
    staleTime: 5 * 60_000,
  });

  const listQ = useQuery({
    queryKey: ['catalog-sources', q, lab, owner, access],
    queryFn: () => {
      const p = new URLSearchParams({ limit: '500' });
      if (q) p.set('q', q);
      if (lab) p.set('lab', lab);
      if (owner) p.set('owner', owner);
      if (access) p.set('access', access);
      return scFetch<CatalogPage>(`/api/v1/admin/catalog/sources?${p.toString()}`);
    },
    staleTime: 60_000,
  });

  const lineageQ = useQuery({
    queryKey: ['catalog-lineage', selected],
    enabled: !!selected,
    queryFn: () =>
      scFetch<LineagePayload>(
        `/api/v1/admin/catalog/sources/${encodeURIComponent(selected as string)}/lineage`,
      ),
    staleTime: 60_000,
  });

  // Client-side freshness filter (server has no freshness param — it is derived).
  const rows = useMemo(() => {
    const items = listQ.data?.items ?? [];
    return freshness ? items.filter((r) => r.freshness === freshness) : items;
  }, [listQ.data, freshness]);

  const selectedCard = useMemo(
    () => rows.find((r) => r.source_id === selected) ?? null,
    [rows, selected],
  );

  const lineageLayout = useMemo(
    () => buildLineageLayout(lineageQ.data),
    [lineageQ.data],
  );

  const catalogAvailable = listQ.data?.available ?? true;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">администрирование · каталог источников</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Database size={22} className="text-copper" /> Source Catalog
        </h1>
        <p className="mt-1 text-sm text-faint">
          Governance-каталог источников: владелец, лаборатория, версия, политика доступа и
          свежесть данных. Клик по источнику открывает карточку и интерактивный lineage-граф
          RAW→Neo4j/Qdrant/OpenSearch.
        </p>

        {/* Filters */}
        <div className="mt-4 flex flex-wrap items-center gap-3 font-mono text-[11px] text-faint">
          <label className="flex items-center gap-1.5 rounded border border-line/60 px-2 py-1">
            <Search size={13} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="поиск по названию / id"
              className="w-52 bg-transparent text-ink outline-none placeholder:text-faint"
            />
          </label>
          <select
            value={lab}
            onChange={(e) => setLab(e.target.value)}
            className="rounded border border-line/60 bg-transparent px-1.5 py-1 text-ink"
          >
            <option value="" className="bg-surface text-ink">
              все лаборатории
            </option>
            {(facetsQ.data?.labs ?? []).map((v) => (
              <option key={v} value={v} className="bg-surface text-ink">
                {v} ({facetsQ.data?.by_lab?.[v] ?? 0})
              </option>
            ))}
          </select>
          <select
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            className="rounded border border-line/60 bg-transparent px-1.5 py-1 text-ink"
          >
            <option value="" className="bg-surface text-ink">
              все владельцы
            </option>
            {(facetsQ.data?.owners ?? []).map((v) => (
              <option key={v} value={v} className="bg-surface text-ink">
                {v}
              </option>
            ))}
          </select>
          <select
            value={access}
            onChange={(e) => setAccess(e.target.value)}
            className="rounded border border-line/60 bg-transparent px-1.5 py-1 text-ink"
          >
            <option value="" className="bg-surface text-ink">
              любой доступ
            </option>
            {(facetsQ.data?.access ?? []).map((v) => (
              <option key={v} value={v} className="bg-surface text-ink">
                {v}
              </option>
            ))}
          </select>
          <select
            value={freshness}
            onChange={(e) => setFreshness(e.target.value)}
            className="rounded border border-line/60 bg-transparent px-1.5 py-1 text-ink"
          >
            <option value="" className="bg-surface text-ink">
              любая свежесть
            </option>
            {['fresh', 'aging', 'stale', 'unknown'].map((v) => (
              <option key={v} value={v} className="bg-surface text-ink">
                {freshMeta(v).ru}
              </option>
            ))}
          </select>
        </div>

        {/* Graceful fallback when catalog is unavailable */}
        {!catalogAvailable && (
          <div className="panel mt-6 flex items-center gap-2 py-6 px-4 font-mono text-[12px] text-faint">
            <CircleOff size={15} className="text-copper" /> Каталог источников недоступен —
            граф не отвечает. Попробуйте позже; данные появятся, когда хранилище вернётся.
          </div>
        )}

        {listQ.isLoading ? (
          <div className="mt-10 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> загрузка каталога…
          </div>
        ) : listQ.isError ? (
          <div
            className="panel mt-8 flex items-center justify-center gap-2 py-8 font-mono text-[12px]"
            style={{ color: '#E5484D' }}
          >
            <TriangleAlert size={15} /> не удалось загрузить /admin/catalog/sources
          </div>
        ) : (
          <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[1.15fr_1fr]">
            {/* Sources table */}
            <div className="panel overflow-hidden">
              <div className="flex items-center justify-between border-b border-line/40 px-3 py-2 font-mono text-[11px] text-faint">
                <span>источников: {rows.length}</span>
                {listQ.data?.has_more && <span>показаны первые {listQ.data.limit}</span>}
              </div>
              <div className="max-h-[560px] overflow-y-auto">
                {rows.length === 0 ? (
                  <div className="py-12 text-center font-mono text-[11px] text-faint">
                    источники не найдены — уточните фильтры или загрузите документы
                  </div>
                ) : (
                  <table className="w-full text-left text-[12px]">
                    <thead className="sticky top-0 bg-panel font-mono text-[10px] uppercase tracking-wide text-faint">
                      <tr>
                        <th className="px-3 py-1.5 font-normal">источник</th>
                        <th className="px-2 py-1.5 font-normal">лаборатория</th>
                        <th className="px-2 py-1.5 font-normal">свежесть</th>
                        <th className="px-2 py-1.5 text-right font-normal">evid.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const fm = freshMeta(r.freshness);
                        const active = r.source_id === selected;
                        return (
                          <tr
                            key={r.source_id}
                            onClick={() => setSelected(r.source_id)}
                            className={`cursor-pointer border-t border-line/30 transition-colors ${
                              active ? 'bg-copper/10' : 'hover:bg-line/10'
                            }`}
                          >
                            <td className="px-3 py-1.5">
                              <div className="font-medium text-ink">
                                {r.name.length > 44 ? r.name.slice(0, 43) + '…' : r.name || r.source_id}
                              </div>
                              <div className="font-mono text-[10px] text-faint">{r.source_id}</div>
                            </td>
                            <td className="px-2 py-1.5 font-mono text-[11px] text-faint">
                              {r.lab || '—'}
                            </td>
                            <td className="px-2 py-1.5">
                              <span
                                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px]"
                                style={{
                                  color: `rgb(${fm.rgb})`,
                                  background: `rgba(${fm.rgb}, 0.12)`,
                                }}
                              >
                                {fm.ru}
                              </span>
                            </td>
                            <td className="px-2 py-1.5 text-right font-mono text-[11px] text-faint">
                              {r.evidence_count}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Source card + lineage */}
            <div className="flex flex-col gap-5">
              {!selectedCard ? (
                <div className="panel flex items-center justify-center py-16 text-center font-mono text-[11px] text-faint">
                  выберите источник слева, чтобы увидеть карточку и lineage-граф
                </div>
              ) : (
                <>
                  {/* Card */}
                  <div className="panel px-4 py-4">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="eyebrow mb-0.5">{selectedCard.label}</div>
                        <div className="font-display text-lg font-semibold text-ink">
                          {selectedCard.name || selectedCard.source_id}
                        </div>
                        <div className="font-mono text-[10px] text-faint">
                          {selectedCard.source_id}
                        </div>
                      </div>
                      <span
                        className="rounded px-2 py-1 font-mono text-[10px]"
                        style={{
                          color: `rgb(${freshMeta(selectedCard.freshness).rgb})`,
                          background: `rgba(${freshMeta(selectedCard.freshness).rgb}, 0.12)`,
                        }}
                      >
                        {freshMeta(selectedCard.freshness).ru}
                        {selectedCard.age_days != null && ` · ${selectedCard.age_days} дн.`}
                      </span>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
                      <CardField
                        icon={<User size={13} />}
                        label="владелец"
                        value={selectedCard.owner || '—'}
                      />
                      <CardField
                        icon={<FlaskConical size={13} />}
                        label="лаборатория"
                        value={selectedCard.lab || '—'}
                      />
                      <CardField
                        icon={<Lock size={13} />}
                        label="доступ"
                        value={selectedCard.access || '—'}
                      />
                      <CardField
                        icon={<GitBranch size={13} />}
                        label="версия"
                        value={`v${selectedCard.version}`}
                      />
                      <CardField
                        icon={<FileText size={13} />}
                        label="evidence / прогоны"
                        value={`${selectedCard.evidence_count} / ${selectedCard.run_count}`}
                      />
                      <CardField
                        icon={<Clock size={13} />}
                        label="последний ingest"
                        value={
                          selectedCard.last_ingest
                            ? selectedCard.last_ingest.slice(0, 10)
                            : '—'
                        }
                      />
                    </div>
                  </div>

                  {/* Lineage graph */}
                  <div className="panel px-4 py-3">
                    <div className="mb-2 flex items-center gap-2 font-mono text-[11px] text-faint">
                      <GitBranch size={14} className="text-copper" /> lineage: RAW →
                      Neo4j / Qdrant / OpenSearch
                    </div>

                    {lineageQ.isLoading ? (
                      <div className="flex items-center gap-2 py-10 font-mono text-[11px] text-faint">
                        <Loader2 size={14} className="animate-spin text-copper" /> строим
                        lineage-граф…
                      </div>
                    ) : !lineageLayout ? (
                      <div className="py-10 text-center font-mono text-[11px] text-faint">
                        lineage недоступен
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <svg
                          viewBox={`0 0 ${lineageLayout.width} ${lineageLayout.height}`}
                          className="w-full"
                          style={{ minWidth: Math.min(lineageLayout.width, 900) }}
                          role="img"
                          aria-label="Lineage-граф источника RAW → Neo4j/Qdrant/OpenSearch"
                        >
                          {/* edges */}
                          <g fill="none">
                            {lineageLayout.edges.map((e, i) => (
                              <path
                                key={i}
                                d={edgePath(e.s, e.t)}
                                stroke="rgba(138,148,158,0.5)"
                                strokeWidth={1.4}
                              />
                            ))}
                          </g>
                          {/* nodes */}
                          <g>
                            {lineageLayout.nodes.map((n) => {
                              const rgb = KIND_RGB[n.kind];
                              const clickable = !!n.deeplink;
                              return (
                                <g
                                  key={n.id}
                                  transform={`translate(${n.x},${n.y})`}
                                  style={{ cursor: clickable ? 'pointer' : 'default' }}
                                  onClick={() =>
                                    n.deeplink && window.open(n.deeplink, '_blank', 'noopener')
                                  }
                                >
                                  <rect
                                    width={NODE_W}
                                    height={NODE_H}
                                    rx={6}
                                    fill={`rgba(${rgb}, 0.14)`}
                                    stroke={`rgba(${rgb}, 0.85)`}
                                    strokeWidth={n.role === 'focus' ? 2 : 1.2}
                                  />
                                  <text
                                    x={10}
                                    y={16}
                                    className="fill-ink"
                                    style={{ fontSize: 11, fontFamily: 'monospace' }}
                                  >
                                    {n.label.length > 18 ? n.label.slice(0, 17) + '…' : n.label}
                                  </text>
                                  <text
                                    x={10}
                                    y={30}
                                    style={{ fontSize: 9, fontFamily: 'monospace', fill: `rgb(${rgb})` }}
                                  >
                                    {n.kind === 'raw'
                                      ? 'RAW'
                                      : n.kind === 'store'
                                        ? (n.platform ?? 'store')
                                        : `шаг ${n.depth}`}
                                  </text>
                                  {clickable && (
                                    <ExternalLink
                                      x={NODE_W - 16}
                                      y={6}
                                      width={10}
                                      height={10}
                                      style={{ color: `rgb(${rgb})` }}
                                    />
                                  )}
                                  <title>{n.urn ? `${n.label}\n${n.urn}` : n.label}</title>
                                </g>
                              );
                            })}
                          </g>
                        </svg>
                      </div>
                    )}

                    {/* legend */}
                    <div className="mt-3 flex flex-wrap items-center gap-4 font-mono text-[10px] text-faint">
                      <span className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ background: `rgb(${KIND_RGB.raw})` }}
                        />
                        источник (RAW)
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ background: `rgb(${KIND_RGB.pipeline})` }}
                        />
                        шаг пайплайна
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ background: `rgb(${KIND_RGB.store})` }}
                        />
                        serving-store
                      </span>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
