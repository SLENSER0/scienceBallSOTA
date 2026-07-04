import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Waypoints, Loader2, TriangleAlert, CircleDashed } from 'lucide-react';

// Потоковая диаграмма покрытия «материал → режим → свойство» (§17.14 / §5.2.7 Gap Dashboard).
//
// Бэкенд `GET /api/v1/coverage/sankey` уже отдаёт готовый сэнки-payload: он
// переиспользует чистый построитель куба покрытия
// `kg_retrievers.coverage_matrix_3d.build_material_regime_property_matrix` (§15.5) и
// сворачивает его в два слоя потоков — material→regime и regime→property. Толщина
// каждого потока = число измерений-доказательств (`value` = evidence count), ровно как
// требует критерий приёмки §17.14 «толщина = evidence/experiment count». Узлы несут
// пропускную способность и число зафиксированных пробелов (для подсветки «слепых»
// режимов и свойств).
//
// Рендер — на чистом SVG (совместимо с текущей сборкой, без внешних chart-зависимостей).
// Точечный апгрейд на ECharts `sankey` series описан в wiring.

type SankeyNode = {
  id: string;
  raw_id: string;
  label: string;
  layer: 0 | 1 | 2;
  kind: 'material' | 'regime' | 'property';
  throughput: number;
  gap_count: number;
};

type SankeyLink = {
  source: string;
  target: string;
  value: number;
  gap_value: number;
};

type SankeyResp = {
  nodes: SankeyNode[];
  links: SankeyLink[];
  summary: {
    materials: number;
    regimes: number;
    properties: number;
    links: number;
    total_evidence: number;
    total_gaps: number;
  };
};

// Человекочитаемые подписи свойств (DEFAULT_PROPERTIES §25).
const PROPERTY_RU: Record<string, string> = {
  recovery: 'Извлечение',
  concentration: 'Концентрация',
  current_density: 'Плотность тока',
  flow_velocity: 'Скорость потока',
  removal_efficiency: 'Степень очистки',
  energy_consumption: 'Энергозатраты',
  capex: 'CapEx',
  opex: 'OpEx',
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

async function skFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// --- Layout geometry (SVG user units; container scrolls if wider than viewport) ----
const W = 1060;
const NODE_W = 14;
const COL_X = [180, 520, 852] as const; // left edge of each column's node rect
const TOP_PAD = 28;
const BOT_PAD = 20;
const NODE_GAP = 8;
const TARGET_COL_H = 560;
const MIN_NODE_H = 6;
const MIN_RIBBON_W = 1.4;

// Per-layer accent colours (read on a dark surface; alpha set at draw time).
const NODE_RGB = {
  material: '184, 115, 51', // copper
  regime: '138, 148, 158', // steel/nickel
  property: '70, 167, 88', // verified green
} as const;

type PlacedNode = SankeyNode & { x: number; y: number; h: number };
type Ribbon = {
  key: string;
  source: string;
  target: string;
  value: number;
  gap_value: number;
  layerFrom: 0 | 1;
  path: string;
};

function buildLayout(data: SankeyResp | undefined) {
  if (!data || data.links.length === 0) return null;

  const byId = new Map(data.nodes.map((n) => [n.id, n]));

  // Per-node in/out sums from the actual (filtered) links → node height = max(in,out),
  // so stacked ribbons never overflow the node rect.
  const inSum = new Map<string, number>();
  const outSum = new Map<string, number>();
  for (const lk of data.links) {
    outSum.set(lk.source, (outSum.get(lk.source) ?? 0) + lk.value);
    inSum.set(lk.target, (inSum.get(lk.target) ?? 0) + lk.value);
  }
  const nodeValue = (id: string) => Math.max(inSum.get(id) ?? 0, outSum.get(id) ?? 0);

  // Group nodes by layer, order by value desc.
  const cols: SankeyNode[][] = [[], [], []];
  for (const n of data.nodes) cols[n.layer].push(n);
  for (const c of cols) c.sort((a, b) => nodeValue(b.id) - nodeValue(a.id) || a.label.localeCompare(b.label));

  // Scale so the heaviest column fills TARGET_COL_H.
  const heaviest = cols.reduce((best, c) => {
    const sum = c.reduce((s, n) => s + nodeValue(n.id), 0);
    return sum > best.sum ? { sum, gaps: Math.max(0, c.length - 1) * NODE_GAP } : best;
  }, { sum: 0, gaps: 0 });
  const scale = heaviest.sum > 0 ? (TARGET_COL_H - heaviest.gaps) / heaviest.sum : 1;

  // Place nodes: each column top-aligned then centred within [TOP_PAD, TOP_PAD+TARGET_COL_H].
  const placed = new Map<string, PlacedNode>();
  cols.forEach((c, layer) => {
    const heights = c.map((n) => Math.max(MIN_NODE_H, nodeValue(n.id) * scale));
    const colH = heights.reduce((s, h) => s + h, 0) + Math.max(0, c.length - 1) * NODE_GAP;
    let cursor = TOP_PAD + Math.max(0, (TARGET_COL_H - colH) / 2);
    c.forEach((n, i) => {
      placed.set(n.id, { ...n, x: COL_X[layer], y: cursor, h: heights[i] });
      cursor += heights[i] + NODE_GAP;
    });
  });

  // Ribbons: stack outgoing on source right edge, incoming on target left edge.
  const outCursor = new Map<string, number>();
  const inCursor = new Map<string, number>();
  const linksSorted = [...data.links].sort((a, b) => {
    const ta = placed.get(a.target)?.y ?? 0;
    const tb = placed.get(b.target)?.y ?? 0;
    return ta - tb;
  });
  const ribbons: Ribbon[] = [];
  for (const lk of linksSorted) {
    const s = placed.get(lk.source);
    const t = placed.get(lk.target);
    if (!s || !t) continue;
    const w = Math.max(MIN_RIBBON_W, lk.value * scale);
    const sy = (outCursor.get(lk.source) ?? s.y);
    const ty = (inCursor.get(lk.target) ?? t.y);
    outCursor.set(lk.source, sy + w);
    inCursor.set(lk.target, ty + w);
    const x0 = s.x + NODE_W;
    const x1 = t.x;
    const xm = (x0 + x1) / 2;
    const path =
      `M${x0},${sy} C${xm},${sy} ${xm},${ty} ${x1},${ty} ` +
      `L${x1},${ty + w} C${xm},${ty + w} ${xm},${sy + w} ${x0},${sy + w} Z`;
    ribbons.push({
      key: `${lk.source}->${lk.target}`,
      source: lk.source,
      target: lk.target,
      value: lk.value,
      gap_value: lk.gap_value,
      layerFrom: (s.layer as 0 | 1),
      path,
    });
  }

  const totalH = TOP_PAD + TARGET_COL_H + BOT_PAD;
  return { nodes: [...placed.values()], ribbons, byId, height: totalH };
}

function ruLabel(n: SankeyNode): string {
  return n.kind === 'property' ? (PROPERTY_RU[n.raw_id] ?? n.label) : n.label;
}

export function CoverageSankeyView() {
  const [materialLimit, setMaterialLimit] = useState(25);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [hover, setHover] = useState<string | null>(null); // node id or ribbon key

  const q = useQuery({
    queryKey: ['coverage-sankey', materialLimit, verifiedOnly],
    queryFn: () =>
      skFetch<SankeyResp>(
        `/api/v1/coverage/sankey?material_limit=${materialLimit}&verified_only=${verifiedOnly}`,
      ),
    staleTime: 5 * 60_000,
  });

  const layout = useMemo(() => buildLayout(q.data), [q.data]);
  const summary = q.data?.summary;

  // A node is "active" when it or an adjacent ribbon is hovered.
  const activeNodes = useMemo(() => {
    const set = new Set<string>();
    if (!layout || !hover) return set;
    if (layout.byId.has(hover)) {
      set.add(hover);
      for (const r of layout.ribbons) {
        if (r.source === hover) set.add(r.target);
        if (r.target === hover) set.add(r.source);
      }
    } else {
      const r = layout.ribbons.find((x) => x.key === hover);
      if (r) {
        set.add(r.source);
        set.add(r.target);
      }
    }
    return set;
  }, [layout, hover]);

  const ribbonActive = (r: Ribbon) => {
    if (!hover) return true;
    if (r.key === hover) return true;
    return r.source === hover || r.target === hover;
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">карта покрытия · потоковая диаграмма</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Waypoints size={22} className="text-copper" /> Потоки покрытия: материал → режим →
          свойство
        </h1>
        <p className="mt-1 text-sm text-faint">
          Толщина потока — число измерений-доказательств, связывающих материал с
          технологическим режимом и режим со свойством. Толстые ленты — хорошо изученные
          связки, тонкие или отсутствующие — «слепые зоны» покрытия. Наведите на узел или
          ленту, чтобы подсветить поток.
        </p>

        {/* Controls */}
        <div className="mt-4 flex flex-wrap items-center gap-3 font-mono text-[11px] text-faint">
          <label className="flex items-center gap-1.5">
            топ материалов
            <select
              value={materialLimit}
              onChange={(e) => setMaterialLimit(Number(e.target.value))}
              className="rounded border border-line/60 bg-transparent px-1.5 py-0.5 text-ink"
            >
              {[10, 15, 25, 40, 60].map((v) => (
                <option key={v} value={v} className="bg-surface text-ink">
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={verifiedOnly}
              onChange={(e) => setVerifiedOnly(e.target.checked)}
              className="accent-copper"
            />
            только подтверждённые
          </label>
        </div>

        {q.isLoading ? (
          <div className="mt-10 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> загрузка потоков покрытия…
          </div>
        ) : q.isError ? (
          <div
            className="panel mt-8 flex items-center justify-center gap-2 py-8 text-center font-mono text-[12px]"
            style={{ color: '#E5484D' }}
          >
            <TriangleAlert size={15} /> не удалось загрузить /coverage/sankey
          </div>
        ) : !layout ? (
          <div className="panel mt-8 py-12 text-center font-mono text-[11px] text-faint">
            нет потоков покрытия — измерений «материал × режим × свойство» не найдено
          </div>
        ) : (
          <>
            {summary && (
              <div className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11px]">
                <span className="chip text-copper border-copper/40">
                  материалов {summary.materials}
                </span>
                <span className="chip text-faint">режимов {summary.regimes}</span>
                <span className="chip text-verified border-verified/40">
                  свойств {summary.properties}
                </span>
                <span className="chip text-faint">потоков {summary.links}</span>
                <span className="chip text-faint">измерений {summary.total_evidence}</span>
                {summary.total_gaps > 0 && (
                  <span className="chip text-gap border-gap/40">пробелов {summary.total_gaps}</span>
                )}
              </div>
            )}

            {/* Column captions */}
            <div className="mt-5 overflow-x-auto">
              <svg
                viewBox={`0 0 ${W} ${layout.height}`}
                className="w-full"
                style={{ minWidth: 760, maxWidth: W }}
                role="img"
                aria-label="Потоковая диаграмма покрытия материал → режим → свойство"
              >
                {/* header labels */}
                <text x={COL_X[0] + NODE_W} y={14} textAnchor="end" className="fill-faint" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                  МАТЕРИАЛ
                </text>
                <text x={COL_X[1] + NODE_W / 2} y={14} textAnchor="middle" className="fill-faint" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                  РЕЖИМ
                </text>
                <text x={COL_X[2]} y={14} textAnchor="start" className="fill-faint" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                  СВОЙСТВО
                </text>

                {/* ribbons (drawn under nodes) */}
                <g>
                  {layout.ribbons.map((r) => {
                    const active = ribbonActive(r);
                    const rgb = r.layerFrom === 0 ? NODE_RGB.material : NODE_RGB.regime;
                    return (
                      <path
                        key={r.key}
                        d={r.path}
                        fill={`rgba(${rgb}, ${active ? (hover ? 0.6 : 0.34) : 0.08})`}
                        stroke={r.gap_value > 0 && active ? `rgba(${NODE_RGB.property}, 0.0)` : 'none'}
                        onMouseEnter={() => setHover(r.key)}
                        onMouseLeave={() => setHover(null)}
                        style={{ cursor: 'pointer', transition: 'fill 120ms' }}
                      >
                        <title>
                          {`${layout.byId.get(r.source)?.label} → ${ruLabel(layout.byId.get(r.target) as SankeyNode)}`}
                          {`\n${r.value} измер.${r.gap_value > 0 ? ` · ${r.gap_value} пробел(ов)` : ''}`}
                        </title>
                      </path>
                    );
                  })}
                </g>

                {/* nodes */}
                <g>
                  {layout.nodes.map((n) => {
                    const rgb = NODE_RGB[n.kind];
                    const active = !hover || activeNodes.has(n.id);
                    const label = ruLabel(n);
                    const labelX =
                      n.layer === 0 ? n.x - 6 : n.layer === 2 ? n.x + NODE_W + 6 : n.x + NODE_W / 2;
                    const anchor = n.layer === 0 ? 'end' : n.layer === 2 ? 'start' : 'middle';
                    const labelY =
                      n.layer === 1 ? n.y - 3 : n.y + Math.min(n.h, Math.max(11, n.h / 2 + 4));
                    return (
                      <g
                        key={n.id}
                        onMouseEnter={() => setHover(n.id)}
                        onMouseLeave={() => setHover(null)}
                        style={{ cursor: 'pointer' }}
                        opacity={active ? 1 : 0.35}
                      >
                        <rect
                          x={n.x}
                          y={n.y}
                          width={NODE_W}
                          height={n.h}
                          rx={2}
                          fill={`rgba(${rgb}, 0.85)`}
                        />
                        {n.gap_count > 0 && (
                          <rect
                            x={n.x}
                            y={n.y}
                            width={NODE_W}
                            height={n.h}
                            rx={2}
                            fill="none"
                            stroke="rgba(226, 84, 61, 0.9)"
                            strokeWidth={1.4}
                            strokeDasharray="3 2"
                          />
                        )}
                        <text
                          x={labelX}
                          y={labelY}
                          textAnchor={anchor}
                          className="fill-ink"
                          style={{ fontSize: n.layer === 1 ? 10 : 11, fontFamily: 'monospace' }}
                        >
                          {label.length > 26 ? label.slice(0, 25) + '…' : label}
                        </text>
                        <title>
                          {`${label}\n${n.throughput} измер.${n.gap_count > 0 ? ` · ${n.gap_count} пробел(ов)` : ''}`}
                        </title>
                      </g>
                    );
                  })}
                </g>
              </svg>
            </div>

            {/* legend */}
            <div className="mt-4 flex flex-wrap items-center gap-4 font-mono text-[10px] text-faint">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `rgb(${NODE_RGB.material})` }} />
                материал
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `rgb(${NODE_RGB.regime})` }} />
                режим
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `rgb(${NODE_RGB.property})` }} />
                свойство
              </span>
              <span className="flex items-center gap-1.5">
                <CircleDashed size={12} className="text-gap" /> пунктир — есть пробел
              </span>
              <span>толщина ленты = число измерений</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
