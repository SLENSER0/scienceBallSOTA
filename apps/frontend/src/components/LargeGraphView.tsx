import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Graph from 'graphology';
import Sigma from 'sigma';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import louvain from 'graphology-communities-louvain';
import { Loader2, Network, ZoomIn, ZoomOut, Maximize2, Play, Filter } from 'lucide-react';

// §17.9 — Large-graph WebGL mode (Sigma.js + Graphology) over the *whole* corpus.
//
// The Reagraph/2D canvas caps a subgraph at ~600 nodes for readability; this view
// instead paints thousands of nodes at once as a fast WebGL overview coloured by
// community. It builds a Graphology graph from the bulk /graph/corpus/overview
// payload, runs forceatlas2 in a *web worker* (no UI freeze), colours by the
// community_id Louvain persisted (falling back to client-side graphology-louvain),
// and renders through Sigma. Left: canvas + minimap + camera controls. Right:
// community summaries (GraphRAG Mode C) — click a community to focus its subgraph;
// click a node for the same detail contract as the Reagraph mode.

// -- domain payload (matches routers/corpus_overview.py) -----------------------
interface OverviewNode {
  id: string;
  name: string;
  type: string;
  communityId: number | null;
  degree: number;
  domain?: string | null;
}
interface OverviewEdge {
  source: string;
  target: string;
  type: string;
  contradicted?: boolean;
  inferred?: boolean;
}
interface CommunityInfo {
  id: number;
  size: number;
  topEntities: string[];
  domains: string[];
  summary: string;
}
interface OverviewStats {
  nodeCount: number;
  edgeCount: number;
  communityCount: number;
  totalNodes: number;
  totalEdges: number;
  truncated: boolean;
}
interface Overview {
  nodes: OverviewNode[];
  edges: OverviewEdge[];
  communities: CommunityInfo[];
  stats: OverviewStats;
}

// Distinct, muted community palette (§5.2.3 colour language: metallic / earthy).
const COMMUNITY_PALETTE = [
  '#C87941', '#6C8CD5', '#5F9E7E', '#E0A23C', '#B26FC8', '#4FA3B8',
  '#D06A6A', '#8FA3B0', '#A9843F', '#7E86C8', '#5FA85F', '#C87FA0',
  '#4F8FB8', '#B8934F', '#7FB89E', '#C85F7A', '#6FB8C8', '#A0A0A0',
];
const DIM = '#2a2f36';
const CONTRA = '#E5484D';

function communityColor(cid: number | null | undefined): string {
  if (cid === null || cid === undefined) return '#8FA3B0';
  return COMMUNITY_PALETTE[((cid % COMMUNITY_PALETTE.length) + COMMUNITY_PALETTE.length) %
    COMMUNITY_PALETTE.length];
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

const BUDGETS = [2000, 6000, 12000, 30000];

export function LargeGraphView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const minimapRef = useRef<HTMLCanvasElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const fa2Ref = useRef<FA2Layout | null>(null);
  const focusRef = useRef<number | null>(null);
  const hoverRef = useRef<string | null>(null);

  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [edgeLimit, setEdgeLimit] = useState(6000);
  const [minDegree, setMinDegree] = useState(1);
  const [selected, setSelected] = useState<OverviewNode | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [running, setRunning] = useState(false);

  focusRef.current = focus;

  // -- fetch bulk corpus overview --------------------------------------------
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const url = `/api/v1/graph/corpus/overview?edge_limit=${edgeLimit}&min_degree=${minDegree}&cluster=true`;
    fetch(url, { headers: { ...authHeaders() } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: Overview) => {
        if (!cancelled) setData(j);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message ?? e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [edgeLimit, minDegree]);

  // -- draw the minimap (node dots + viewport rect) --------------------------
  const drawMinimap = useCallback(() => {
    const cv = minimapRef.current;
    const sigma = sigmaRef.current;
    const graph = graphRef.current;
    if (!cv || !sigma || !graph) return;
    const ctx = cv.getContext('2d');
    if (!ctx) return;
    const W = cv.width;
    const H = cv.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillRect(0, 0, W, H);
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    graph.forEachNode((_n, a) => {
      if (a.x < minX) minX = a.x;
      if (a.x > maxX) maxX = a.x;
      if (a.y < minY) minY = a.y;
      if (a.y > maxY) maxY = a.y;
    });
    if (!isFinite(minX)) return;
    const sx = (x: number) => ((x - minX) / (maxX - minX || 1)) * (W - 8) + 4;
    const sy = (y: number) => ((y - minY) / (maxY - minY || 1)) * (H - 8) + 4;
    graph.forEachNode((_n, a) => {
      ctx.fillStyle = a.color ?? '#8FA3B0';
      ctx.fillRect(sx(a.x), sy(a.y), 1.4, 1.4);
    });
    // viewport rectangle from camera graph-space bounds
    try {
      const tl = sigma.viewportToGraph({ x: 0, y: 0 });
      const br = sigma.viewportToGraph({ x: sigma.getContainer().offsetWidth, y: sigma.getContainer().offsetHeight });
      ctx.strokeStyle = '#C87941';
      ctx.lineWidth = 1;
      ctx.strokeRect(sx(tl.x), sy(tl.y), sx(br.x) - sx(tl.x), sy(br.y) - sy(tl.y));
    } catch {
      /* camera not ready */
    }
  }, []);

  // -- build the Graphology graph + Sigma renderer ----------------------------
  useEffect(() => {
    if (!data || !containerRef.current) return;
    // teardown previous
    fa2Ref.current?.kill();
    sigmaRef.current?.kill();
    fa2Ref.current = null;
    sigmaRef.current = null;

    const graph = new Graph({ multi: false, type: 'undirected' });
    const maxDeg = data.nodes.reduce((m, n) => Math.max(m, n.degree), 1);
    for (const n of data.nodes) {
      if (graph.hasNode(n.id)) continue;
      graph.addNode(n.id, {
        label: n.name,
        x: Math.random(),
        y: Math.random(),
        size: 2 + Math.sqrt(n.degree / maxDeg) * 10,
        color: communityColor(n.communityId),
        community: n.communityId,
        ntype: n.type,
        degree: n.degree,
      });
    }
    for (const e of data.edges) {
      if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
      if (graph.hasEdge(e.source, e.target)) continue;
      graph.addEdge(e.source, e.target, {
        size: e.contradicted ? 1.4 : 0.5,
        color: e.contradicted ? CONTRA : '#3a4048',
        contradicted: !!e.contradicted,
        inferred: !!e.inferred,
      });
    }

    // Fallback community detection (§17.9 graphology-communities-louvain) when the
    // backend has no community_id yet — colour + community attr set client-side.
    const hasBackendCommunities = data.nodes.some((n) => n.communityId !== null);
    if (!hasBackendCommunities && graph.order > 0) {
      try {
        louvain.assign(graph, { nodeCommunityAttribute: 'community' });
        graph.forEachNode((n, a) => {
          graph.setNodeAttribute(n, 'color', communityColor((a as { community: number }).community));
        });
      } catch {
        /* leave type colours */
      }
    }
    graphRef.current = graph;

    const sigma = new Sigma(graph, containerRef.current, {
      renderLabels: true,
      labelRenderedSizeThreshold: 12,
      defaultEdgeColor: '#3a4048',
      minCameraRatio: 0.02,
      maxCameraRatio: 12,
      labelColor: { color: '#c7ced6' },
      labelFont: 'IBM Plex Sans, sans-serif',
    });
    sigmaRef.current = sigma;

    // Reducers: community focus dims non-members; hover highlights neighbourhood.
    sigma.setSetting('nodeReducer', (node, attrs) => {
      const f = focusRef.current;
      const res = { ...attrs } as Record<string, unknown> & { color: string; hidden?: boolean };
      if (f !== null && attrs.community !== f) {
        res.color = DIM;
        res.label = '';
        res.size = Math.max(1, (attrs.size as number) * 0.5);
      }
      const hv = hoverRef.current;
      if (hv && node === hv) {
        res.highlighted = true;
      }
      return res;
    });
    sigma.setSetting('edgeReducer', (edge, attrs) => {
      const f = focusRef.current;
      const res = { ...attrs } as Record<string, unknown> & { hidden?: boolean };
      if (f !== null) {
        const [s, t] = graph.extremities(edge);
        const inFocus =
          graph.getNodeAttribute(s, 'community') === f &&
          graph.getNodeAttribute(t, 'community') === f;
        if (!inFocus) res.hidden = true;
      }
      return res;
    });

    sigma.on('clickNode', ({ node }) => {
      setSelected({
        id: node,
        name: graph.getNodeAttribute(node, 'label'),
        type: graph.getNodeAttribute(node, 'ntype'),
        communityId: graph.getNodeAttribute(node, 'community'),
        degree: graph.getNodeAttribute(node, 'degree'),
      });
    });
    sigma.on('enterNode', ({ node }) => {
      hoverRef.current = node;
      sigma.refresh();
    });
    sigma.on('leaveNode', () => {
      hoverRef.current = null;
      sigma.refresh();
    });
    sigma.on('clickStage', () => setSelected(null));
    sigma.on('afterRender', drawMinimap);

    // ForceAtlas2 in a *web worker* — layout without freezing the UI (§17.9).
    const settings = forceAtlas2.inferSettings(graph);
    const fa2 = new FA2Layout(graph, {
      settings: { ...settings, slowDown: 1 + Math.log(Math.max(2, graph.order)) },
    });
    fa2Ref.current = fa2;
    fa2.start();
    setRunning(true);
    const stop = window.setTimeout(() => {
      fa2.stop();
      setRunning(false);
      sigma.getCamera().animatedReset();
      drawMinimap();
    }, 4500);

    return () => {
      window.clearTimeout(stop);
      fa2.kill();
      sigma.kill();
      fa2Ref.current = null;
      sigmaRef.current = null;
      graphRef.current = null;
    };
  }, [data, drawMinimap]);

  // Recompute reducers when focus changes.
  useEffect(() => {
    sigmaRef.current?.refresh();
  }, [focus]);

  const focusCommunity = useCallback((cid: number) => {
    setFocus((cur) => {
      const next = cur === cid ? null : cid;
      // Reducers (below) dim non-members; reset the camera so the focused
      // cluster fills the view. Fine-grained bbox zoom is intentionally avoided
      // to keep the camera math renderer-version-agnostic.
      sigmaRef.current?.getCamera().animatedReset({ duration: 400 });
      return next;
    });
  }, []);

  const rerunLayout = useCallback(() => {
    const fa2 = fa2Ref.current;
    if (!fa2) return;
    fa2.start();
    setRunning(true);
    window.setTimeout(() => {
      fa2.stop();
      setRunning(false);
    }, 3500);
  }, []);

  const zoom = (dir: 'in' | 'out' | 'reset') => {
    const cam = sigmaRef.current?.getCamera();
    if (!cam) return;
    if (dir === 'in') cam.animatedZoom({ duration: 300 });
    else if (dir === 'out') cam.animatedUnzoom({ duration: 300 });
    else cam.animatedReset({ duration: 300 });
  };

  const stats = data?.stats;
  const legend = useMemo(() => (data?.communities ?? []).slice(0, 12), [data]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-6 py-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-nickel">
          <Network size={20} className="text-copper" /> Клубок корпуса
          <span className="font-mono text-[11px] font-normal text-faint">Sigma · WebGL · §17.9</span>
        </h2>
        <div className="ml-auto flex items-center gap-2 font-mono text-[11px] text-faint">
          <Filter size={13} />
          <span>бюджет:</span>
          {BUDGETS.map((b) => (
            <button
              key={b}
              onClick={() => setEdgeLimit(b)}
              className={`rounded px-1.5 py-0.5 ${
                edgeLimit === b ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
              }`}
            >
              {b >= 1000 ? `${b / 1000}k` : b}
            </button>
          ))}
          <span className="ml-2">степень ≥</span>
          <button
            onClick={() => setMinDegree((d) => (d === 1 ? 2 : d === 2 ? 3 : 1))}
            className="rounded bg-line px-1.5 py-0.5 text-nickel"
          >
            {minDegree}
          </button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {/* graph canvas */}
        <div className="relative min-h-0 flex-1">
          <div ref={containerRef} className="absolute inset-0 bg-[#12151a]" />

          {loading && (
            <div className="absolute inset-0 flex items-center justify-center gap-2 font-mono text-sm text-faint">
              <Loader2 size={16} className="animate-spin text-copper" /> загрузка корпуса…
            </div>
          )}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center font-mono text-sm text-[#E5484D]">
              ошибка загрузки графа: {error}
            </div>
          )}

          {/* camera controls */}
          <div className="absolute right-3 top-3 flex flex-col gap-1.5">
            <IconBtn onClick={() => zoom('in')} title="приблизить"><ZoomIn size={15} /></IconBtn>
            <IconBtn onClick={() => zoom('out')} title="отдалить"><ZoomOut size={15} /></IconBtn>
            <IconBtn onClick={() => zoom('reset')} title="вписать"><Maximize2 size={15} /></IconBtn>
            <IconBtn onClick={rerunLayout} title="пересчитать раскладку">
              {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            </IconBtn>
          </div>

          {/* minimap */}
          <div className="absolute bottom-3 left-3 overflow-hidden rounded border border-line">
            <canvas ref={minimapRef} width={180} height={120} className="block" />
          </div>

          {/* stats + running badge */}
          {stats && (
            <div className="absolute left-3 top-3 rounded bg-black/40 px-2 py-1 font-mono text-[10px] text-faint">
              {stats.nodeCount.toLocaleString()} узлов · {stats.edgeCount.toLocaleString()} рёбер ·{' '}
              {stats.communityCount} сообществ
              {stats.truncated && <span className="text-copper"> · срез {stats.totalNodes.toLocaleString()}</span>}
              {running && <span className="text-copper"> · forceatlas2…</span>}
            </div>
          )}

          {/* selected-node detail (same contract as Reagraph mode) */}
          {selected && (
            <div className="absolute bottom-3 right-3 w-64 rounded-lg border border-line bg-panel/95 p-3 text-sm shadow-xl backdrop-blur">
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ background: communityColor(selected.communityId) }}
                />
                <span className="font-semibold text-nickel">{selected.name}</span>
              </div>
              <dl className="mt-2 space-y-1 font-mono text-[11px] text-faint">
                <div className="flex justify-between"><dt>тип</dt><dd className="text-nickel">{selected.type}</dd></div>
                <div className="flex justify-between"><dt>степень</dt><dd className="text-nickel">{selected.degree}</dd></div>
                <div className="flex justify-between">
                  <dt>сообщество</dt>
                  <dd className="text-nickel">{selected.communityId ?? '—'}</dd>
                </div>
                <div className="truncate"><dt className="inline">id: </dt><dd className="inline text-nickel">{selected.id}</dd></div>
              </dl>
              {selected.communityId !== null && (
                <button
                  onClick={() => focusCommunity(selected.communityId as number)}
                  className="mt-2 w-full rounded bg-copper/20 py-1 text-[11px] text-copper hover:bg-copper/30"
                >
                  {focus === selected.communityId ? 'снять фокус' : 'фокус на сообществе'}
                </button>
              )}
            </div>
          )}
        </div>

        {/* community summaries panel (GraphRAG Mode C §10) */}
        <aside className="flex w-72 min-w-72 flex-col border-l border-line">
          <div className="border-b border-line px-4 py-2.5 font-mono text-[11px] uppercase tracking-wide text-faint">
            Сообщества корпуса
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {legend.length === 0 && !loading && (
              <p className="px-4 py-6 text-center font-mono text-[11px] text-faint">
                кластеры не обнаружены
              </p>
            )}
            {legend.map((c) => (
              <button
                key={c.id}
                onClick={() => focusCommunity(c.id)}
                className={`block w-full border-b border-line/60 px-4 py-3 text-left transition-colors ${
                  focus === c.id ? 'bg-copper/10' : 'hover:bg-line/40'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 rounded-sm"
                    style={{ background: communityColor(c.id) }}
                  />
                  <span className="text-sm font-medium text-nickel">
                    {c.topEntities[0] ?? `Кластер #${c.id}`}
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-faint">{c.size}</span>
                </div>
                {c.summary ? (
                  <p className="mt-1.5 line-clamp-3 text-[12px] leading-snug text-faint">{c.summary}</p>
                ) : (
                  <p className="mt-1.5 line-clamp-2 text-[12px] leading-snug text-faint">
                    {c.topEntities.slice(0, 5).join(', ')}
                  </p>
                )}
                {c.domains.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {c.domains.slice(0, 3).map((d) => (
                      <span key={d} className="chip text-[9px] text-faint">{d}</span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}

function IconBtn({
  onClick,
  title,
  children,
}: {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="grid h-8 w-8 place-items-center rounded border border-line bg-panel/80 text-nickel backdrop-blur hover:bg-line"
    >
      {children}
    </button>
  );
}
