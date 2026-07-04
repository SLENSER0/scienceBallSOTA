import { useCallback, useEffect, useRef, useState } from 'react';
import Graph from 'graphology';
import Sigma from 'sigma';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import { Boxes, Loader2, Network, Sparkles, RefreshCw } from 'lucide-react';

// §11.8 — Community-cluster overview graph (GraphRAG Mode C, «глобальный взгляд»).
//
// Мета-карта корпуса: КАЖДЫЙ узел — это целый кластер знаний (community), а не
// отдельная сущность. Размер узла ∝ числу сущностей в кластере, рёбра RELATED —
// сколько связей между сущностями двух кластеров (какие темы «соприкасаются»).
// Рисуем через Sigma.js + Graphology (тот же WebGL-стек, что «Клубок корпуса»,
// §17.9 / §18 «Graph becomes unreadable → community view, Sigma fallback»), но на
// десятках узлов-кластеров вместо 30k сущностей — обзорный ответ Mode C становится
// интерактивным графом. Клик по кластеру → карточка со сводкой и top-сущностями.
//
// Payload читаем напрямую (self-contained, как LargeGraphView), формат
// Reagraph-shaped — см. routers/community_cluster_graph.py.

interface ClusterNode {
  id: string;
  label: string;
  type: 'community' | 'entity';
  community_id: number;
  size?: number;
  domains?: string[];
  top_entities?: string[];
}
interface ClusterEdge {
  source: string;
  target: string;
  type: 'RELATED' | 'INCLUDES_ENTITY';
  weight: number;
}
interface ClusterGraph {
  clustered: boolean;
  total_communities: number;
  count: number;
  nodes: ClusterNode[];
  edges: ClusterEdge[];
  stats: { clustered_nodes: number; related_edges: number; entity_edges: number };
}

// Metallic / earthy community palette (§5.2.3), shared language with LargeGraphView.
const PALETTE = [
  '#C87941', '#6C8CD5', '#5F9E7E', '#E0A23C', '#B26FC8', '#4FA3B8',
  '#D06A6A', '#8FA3B0', '#A9843F', '#7E86C8', '#5FA85F', '#C87FA0',
  '#4F8FB8', '#B8934F', '#7FB89E', '#C85F7A', '#6FB8C8', '#A0A0A0',
];
const DIM = '#2a2f36';

function clusterColor(cid: number): string {
  return PALETTE[((cid % PALETTE.length) + PALETTE.length) % PALETTE.length];
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

export function CommunityClusterGraphView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const focusRef = useRef<string | null>(null);

  const [data, setData] = useState<ClusterGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ClusterNode | null>(null);
  const [reload, setReload] = useState(0);

  // -- fetch the cluster meta-graph ------------------------------------------
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const url = '/api/v1/community-cluster-graph?min_size=2&limit=48&max_entities=6';
    fetch(url, { headers: { ...authHeaders() } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: ClusterGraph) => {
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
  }, [reload]);

  // -- build Graphology graph + Sigma renderer -------------------------------
  useEffect(() => {
    if (!data || !containerRef.current) return;
    sigmaRef.current?.kill();
    sigmaRef.current = null;

    const communities = data.nodes.filter((n) => n.type === 'community');
    const maxSize = communities.reduce((m, n) => Math.max(m, n.size ?? 1), 1);
    const maxWeight = data.edges.reduce((m, e) => Math.max(m, e.weight), 1);

    const graph = new Graph({ multi: false, type: 'undirected' });
    // Circular seed positions → forceatlas2 spreads clusters out from there.
    const N = data.nodes.length || 1;
    data.nodes.forEach((n, i) => {
      if (graph.hasNode(n.id)) return;
      const angle = (2 * Math.PI * i) / N;
      const isCommunity = n.type === 'community';
      graph.addNode(n.id, {
        label: n.label,
        x: Math.cos(angle) + Math.random() * 0.05,
        y: Math.sin(angle) + Math.random() * 0.05,
        size: isCommunity ? 4 + Math.sqrt((n.size ?? 1) / maxSize) * 20 : 3,
        color: isCommunity ? clusterColor(n.community_id) : '#6b7480',
        ntype: n.type,
        community: n.community_id,
        payload: n,
      });
    });
    for (const e of data.edges) {
      if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
      if (graph.hasEdge(e.source, e.target)) continue;
      const isRelated = e.type === 'RELATED';
      graph.addEdge(e.source, e.target, {
        size: isRelated ? 0.6 + (e.weight / maxWeight) * 5 : 0.4,
        color: isRelated ? '#55606c' : '#3a4048',
        etype: e.type,
        weight: e.weight,
      });
    }
    graphRef.current = graph;

    // Synchronous forceatlas2 — the meta-graph is small (dozens of nodes), no
    // web-worker needed; a few hundred iterations settle the layout instantly.
    if (graph.order > 1) {
      try {
        const settings = forceAtlas2.inferSettings(graph);
        forceAtlas2.assign(graph, {
          iterations: 300,
          settings: { ...settings, scalingRatio: 12, gravity: 1.2 },
        });
      } catch {
        /* keep circular seed positions */
      }
    }

    const sigma = new Sigma(graph, containerRef.current, {
      renderLabels: true,
      labelRenderedSizeThreshold: 6,
      defaultEdgeColor: '#3a4048',
      minCameraRatio: 0.05,
      maxCameraRatio: 8,
      labelColor: { color: '#c7ced6' },
      labelFont: 'IBM Plex Sans, sans-serif',
    });
    sigmaRef.current = sigma;

    // Focus reducer: clicking a cluster dims everything not adjacent to it.
    sigma.setSetting('nodeReducer', (node, attrs) => {
      const f = focusRef.current;
      const res = { ...attrs } as Record<string, unknown> & { color: string; label?: string };
      if (f && node !== f && !graph.areNeighbors(f, node)) {
        res.color = DIM;
        res.label = '';
      }
      return res;
    });
    sigma.setSetting('edgeReducer', (edge, attrs) => {
      const f = focusRef.current;
      const res = { ...attrs } as Record<string, unknown> & { hidden?: boolean };
      if (f) {
        const [s, t] = graph.extremities(edge);
        if (s !== f && t !== f) res.hidden = true;
      }
      return res;
    });

    sigma.on('clickNode', ({ node }) => {
      const payload = graph.getNodeAttribute(node, 'payload') as ClusterNode;
      focusRef.current = node;
      setSelected(payload);
      sigma.refresh();
    });
    sigma.on('clickStage', () => {
      focusRef.current = null;
      setSelected(null);
      sigma.refresh();
    });

    sigma.getCamera().animatedReset();

    return () => {
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
      focusRef.current = null;
    };
  }, [data]);

  const clearFocus = useCallback(() => {
    focusRef.current = null;
    setSelected(null);
    sigmaRef.current?.refresh();
  }, []);

  const communityCount = data?.nodes.filter((n) => n.type === 'community').length ?? 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <div className="eyebrow mb-1">GraphRAG · community-cluster граф · §11.8</div>
          <h1 className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
            <Sparkles size={18} className="text-copper" /> Карта кластеров знаний
          </h1>
          <p className="mt-1 max-w-2xl text-xs text-faint">
            Глобальный взгляд на корпус (Mode C): каждый узел — целый кластер знаний,
            размер ∝ числу сущностей, ребро — сколько связей между темами. Клик по
            кластеру раскрывает сводку и ключевые сущности.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {data && (
            <span className="chip text-faint">
              {communityCount} кластеров · {data.stats.related_edges} связей
            </span>
          )}
          <button
            onClick={() => setReload((r) => r + 1)}
            className="chip flex items-center gap-1 hover:border-copper/50 hover:text-copper"
            title="пересчитать"
          >
            <RefreshCw size={12} /> обновить
          </button>
        </div>
      </div>

      {/* Canvas + side panel */}
      <div className="relative flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {loading ? (
            <div className="flex h-full items-center justify-center font-mono text-sm text-faint">
              <Loader2 size={15} className="mr-2 animate-spin text-copper" /> детекция сообществ…
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center px-6 text-center font-mono text-[11px] text-red-400">
              ошибка загрузки мета-графа: {error}
            </div>
          ) : communityCount === 0 ? (
            <div className="flex h-full items-center justify-center font-mono text-[11px] text-faint">
              кластеры знаний не найдены — корпус ещё не кластеризован
            </div>
          ) : (
            <>
              <div ref={containerRef} className="absolute inset-0" />
              <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-line bg-graphite/70 px-2.5 py-1.5 font-mono text-[10px] text-faint">
                узел = кластер · размер ∝ сущностей · ребро = связи между темами
              </div>
            </>
          )}
        </div>

        {/* Selected cluster detail */}
        {selected && selected.type === 'community' && (
          <div className="w-[340px] shrink-0 overflow-y-auto border-l border-line px-4 py-4">
            <div className="flex items-center gap-2">
              <span
                className="h-3 w-3 shrink-0 rounded-full"
                style={{ backgroundColor: clusterColor(selected.community_id) }}
              />
              <span className="truncate text-sm font-medium text-ink">{selected.label}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="chip text-faint">
                <Boxes size={11} className="mr-1" />
                {selected.size ?? 0} сущностей
              </span>
              <button onClick={clearFocus} className="chip ml-auto hover:text-copper">
                сброс, фокус
              </button>
            </div>
            {selected.domains && selected.domains.length > 0 && (
              <div className="mt-3">
                <div className="eyebrow mb-1.5">Домены</div>
                <div className="flex flex-wrap gap-1">
                  {selected.domains.map((d) => (
                    <span key={d} className="chip text-[10px] text-copper">
                      {DOMAIN_RU[d] ?? d}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {selected.top_entities && selected.top_entities.length > 0 && (
              <div className="mt-3">
                <div className="eyebrow mb-1.5">Ключевые сущности</div>
                <div className="space-y-1">
                  {selected.top_entities.map((e) => (
                    <div
                      key={e}
                      className="flex items-center gap-1.5 rounded border border-line px-2 py-1 text-xs text-muted"
                    >
                      <Network size={11} className="shrink-0 text-faint" />
                      <span className="truncate">{e}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
