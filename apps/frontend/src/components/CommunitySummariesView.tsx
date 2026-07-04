import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
} from 'd3-force';
import { Boxes, Loader2, Network, Sparkles } from 'lucide-react';
import { api } from '../api';
import type { CommunitySummary, GraphNode, GraphResponse } from '../types';

// Панель community summaries (GraphRAG Mode C §11 / §17.9, SOTA #3).
// Слева — текстовые сводки кластеров знаний (их пишет detect_communities как
// Finding-узлы), справа — cluster-раскраска: клик по сводке фокусирует подграф
// этого сообщества на canvas force-graph. Так broad-вопрос («что вообще есть в
// корпусе») объясняется структурой графа, а не плоским списком.

// Deterministic cluster palette — same community_id ⇒ same colour on card + graph.
const CLUSTER_COLORS = [
  '#C87941',
  '#6C8CD5',
  '#5F9E7F',
  '#E0A23C',
  '#B072C4',
  '#4FA6B8',
  '#D46A6A',
  '#8FA3B0',
  '#E89B5C',
  '#7D8CC4',
];

function clusterColor(cid: number): string {
  return CLUSTER_COLORS[((cid % CLUSTER_COLORS.length) + CLUSTER_COLORS.length) % CLUSTER_COLORS.length];
}

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  environment: 'Экология',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электромет',
};

export function CommunitySummariesView() {
  const [selected, setSelected] = useState<number | null>(null);

  const list = useQuery({
    queryKey: ['community-summaries'],
    queryFn: () => api.communitySummaries(60),
    staleTime: 5 * 60_000,
  });
  const communities = list.data?.communities ?? [];

  // Auto-select the largest community once summaries arrive.
  useEffect(() => {
    if (selected === null && communities.length > 0) {
      setSelected(communities[0].community_id);
    }
  }, [communities, selected]);

  const active = communities.find((c) => c.community_id === selected) ?? null;

  return (
    <div className="flex h-full min-h-0">
      {/* Left: community summaries */}
      <div className="flex w-[420px] shrink-0 flex-col border-r border-line">
        <div className="border-b border-line px-5 py-4">
          <div className="eyebrow mb-1">GraphRAG · community summaries · §17.9</div>
          <h1 className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
            <Sparkles size={18} className="text-copper" /> Сводки по кластерам знаний
          </h1>
          <p className="mt-1 text-xs text-faint">
            Обзор структуры корпуса: каждое сообщество графа получает текстовую сводку. Клик по
            сводке фокусирует подграф этого кластера справа.
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {list.isLoading ? (
            <div className="flex items-center gap-2 px-2 py-6 font-mono text-sm text-faint">
              <Loader2 size={15} className="animate-spin text-copper" /> детекция сообществ…
            </div>
          ) : communities.length === 0 ? (
            <div className="panel py-10 text-center font-mono text-[11px] text-faint">
              кластеры знаний не найдены
            </div>
          ) : (
            <div className="space-y-2">
              {communities.map((c) => (
                <CommunityCard
                  key={c.community_id}
                  c={c}
                  active={c.community_id === selected}
                  onClick={() => setSelected(c.community_id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: cluster-coloured subgraph focus */}
      <div className="min-w-0 flex-1">
        {active ? (
          <CommunityFocus community={active} />
        ) : (
          <div className="flex h-full items-center justify-center text-faint">
            <div className="text-center">
              <Network size={28} className="mx-auto mb-2 opacity-40" />
              <div className="font-mono text-[11px]">выберите сообщество слева</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CommunityCard({
  c,
  active,
  onClick,
}: {
  c: CommunitySummary;
  active: boolean;
  onClick: () => void;
}) {
  const color = clusterColor(c.community_id);
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-md border p-3 text-left transition-colors ${
        active ? 'border-copper/60 bg-copper/5' : 'border-line hover:border-nickel/40 hover:bg-surface/50'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: color }} />
        <span className="truncate text-sm font-medium text-ink">{c.title}</span>
        <span className="chip ml-auto shrink-0 text-faint">{c.size} сущ.</span>
      </div>
      {c.summary && <p className="mt-1.5 line-clamp-3 text-xs text-muted">{c.summary}</p>}
      {(c.domains.length > 0 || c.top_entities.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1">
          {c.domains.map((d) => (
            <span key={d} className="chip text-[10px] text-copper">
              {DOMAIN_RU[d] ?? d}
            </span>
          ))}
          {c.top_entities.slice(0, 4).map((e) => (
            <span key={e} className="chip text-[10px] text-faint">
              {e}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function CommunityFocus({ community }: { community: CommunitySummary }) {
  const q = useQuery({
    queryKey: ['community-subgraph', community.community_id],
    queryFn: () => api.communitySubgraph(community.community_id, 1),
    staleTime: 5 * 60_000,
  });
  const graph: GraphResponse | undefined = q.data;
  const color = clusterColor(community.community_id);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-line px-5 py-3">
        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
        <span className="text-sm font-medium text-ink">{community.title}</span>
        <span className="chip text-faint">
          <Boxes size={11} className="mr-1" />
          {community.size} сущностей
        </span>
        {graph && (
          <span className="chip ml-auto text-faint">
            {graph.nodes.length} узлов · {graph.edges.length} связей
          </span>
        )}
      </div>
      <div className="relative min-h-0 flex-1">
        {q.isLoading ? (
          <div className="flex h-full items-center justify-center font-mono text-sm text-faint">
            <Loader2 size={15} className="mr-2 animate-spin text-copper" /> построение подграфа…
          </div>
        ) : graph && graph.nodes.length > 0 ? (
          <ClusterCanvas graph={graph} focusCid={community.community_id} />
        ) : (
          <div className="flex h-full items-center justify-center font-mono text-[11px] text-faint">
            подграф пуст
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Compact d3-force canvas, coloured by community (cluster-раскраска) ------

type SimNode = GraphNode & { x: number; y: number; fx?: number | null; fy?: number | null; r: number };
type SimLink = { source: SimNode; target: SimNode };

function ClusterCanvas({ graph, focusCid }: { graph: GraphResponse; focusCid: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  // Observe container size.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const { nodes, links } = useMemo(() => {
    const byId = new Map<string, SimNode>();
    const ns: SimNode[] = graph.nodes.map((n) => {
      const sn: SimNode = { ...n, x: Math.random() * 400, y: Math.random() * 400, r: 5 };
      byId.set(n.id, sn);
      return sn;
    });
    const ls: SimLink[] = [];
    for (const e of graph.edges) {
      const s = byId.get(e.source);
      const t = byId.get(e.target);
      if (s && t) ls.push({ source: s, target: t });
    }
    // degree → radius
    const deg = new Map<string, number>();
    for (const l of ls) {
      deg.set(l.source.id, (deg.get(l.source.id) ?? 0) + 1);
      deg.set(l.target.id, (deg.get(l.target.id) ?? 0) + 1);
    }
    for (const n of ns) n.r = 4 + Math.min(8, deg.get(n.id) ?? 0);
    return { nodes: ns, links: ls };
  }, [graph]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Non-null assertion so `ctx` stays typed inside the nested draw() closure
    // (TS resets flow-narrowing across closure boundaries).
    const ctx = canvas.getContext('2d')!;
    if (!ctx) return;
    const { w, h } = size;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const sim = forceSimulation<SimNode>(nodes)
      .force('charge', forceManyBody().strength(-140))
      .force('link', forceLink<SimNode, SimLink>(links).distance(60).strength(0.5))
      .force('center', forceCenter(w / 2, h / 2))
      .force('collide', forceCollide<SimNode>().radius((d) => d.r + 3));
    simRef.current = sim;

    function draw() {
      ctx.clearRect(0, 0, w, h);
      // edges
      ctx.strokeStyle = 'rgba(143,163,176,0.25)';
      ctx.lineWidth = 1;
      for (const l of links) {
        ctx.beginPath();
        ctx.moveTo(l.source.x, l.source.y);
        ctx.lineTo(l.target.x, l.target.y);
        ctx.stroke();
      }
      // nodes
      ctx.font = '10px ui-sans-serif, system-ui';
      for (const n of nodes) {
        const cid = n.communityId;
        const inFocus = cid === focusCid || cid == null;
        ctx.globalAlpha = inFocus ? 1 : 0.35;
        ctx.fillStyle = cid != null ? clusterColor(cid) : '#5A6270';
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fill();
        if (n.r >= 7) {
          ctx.globalAlpha = inFocus ? 0.85 : 0.3;
          ctx.fillStyle = '#C9D3DA';
          const name = (n.properties?.name as string) || n.id;
          ctx.fillText(String(name).slice(0, 22), n.x + n.r + 2, n.y + 3);
        }
      }
      ctx.globalAlpha = 1;
    }

    sim.on('tick', draw);
    draw();
    return () => {
      sim.stop();
    };
  }, [nodes, links, size, focusCid]);

  return (
    <div ref={wrapRef} className="absolute inset-0">
      <canvas ref={canvasRef} className="h-full w-full" />
      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-line bg-graphite/70 px-2.5 py-1.5 font-mono text-[10px] text-faint">
        cluster-раскраска по community_id · выделен #{focusCid}
      </div>
    </div>
  );
}
