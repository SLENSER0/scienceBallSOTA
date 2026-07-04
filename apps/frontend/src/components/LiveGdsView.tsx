import { lazy, Suspense, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Network, Play, Sparkles, TriangleAlert, Wand2 } from 'lucide-react';
import { api } from '../api';
import type { GraphResponse } from '../types';

// §3.14 «Живой GDS на Neo4j»: Louvain-сообщества + nodeSimilarity на боевой БД,
// раскраска кластеров прямо в 3D-клубке. До сих пор GDS жил только в embedded
// (NetworkX); здесь — настоящие CALL gds на живом Neo4j (server-профиль :8000).

// Heavy three.js bundle — грузим лениво, только когда открыт этот экран.
const ForceGraph3D = lazy(() => import('react-force-graph-3d'));

// Палитра сообществ: цвет = COMMUNITY_COLORS[community_id % N]. Ту же формулу
// использует легенда и клубок, поэтому чип и узел совпадают по цвету.
const COMMUNITY_COLORS = [
  '#C87941', '#6C8CD5', '#4FA88B', '#E0A23C', '#B4639E',
  '#5B9BD5', '#E5744D', '#7FB069', '#9B7EDE', '#D4A05B',
  '#5FA8A0', '#E06C8A', '#8FA3B0', '#C0985A', '#6FBF73',
  '#D08770', '#A3BE8C', '#B48EAD', '#88C0D0', '#EBCB8B',
];
const NO_COMMUNITY = '#3A414D';

function communityColor(id: number | null | undefined): string {
  if (id === null || id === undefined) return NO_COMMUNITY;
  return COMMUNITY_COLORS[((id % COMMUNITY_COLORS.length) + COMMUNITY_COLORS.length) % COMMUNITY_COLORS.length];
}

interface CommunityRow {
  community_id: number;
  size: number;
  top_entities: string[];
}
interface CommunitiesResponse {
  clustered: boolean;
  count: number;
  communities: CommunityRow[];
}
interface GdsStatus {
  available: boolean;
  profile: string;
  clustered?: boolean;
  communities?: number;
  reason?: string;
}
interface LouvainResult {
  run_id: string;
  community_count: number;
  modularity: number;
  nodes_written: number;
  projected: { nodes: number; relationships: number };
  communities: CommunityRow[];
}
interface SimilarResponse {
  seed: { id: string; name?: string; label?: string };
  count: number;
  similar: { id: string; name: string; label?: string; similarity: number }[];
}

function ColoredGraph({ data }: { data: GraphResponse }) {
  const graph = useMemo(() => {
    const deg = new Map<string, number>();
    for (const e of data.edges) {
      deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
      deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    }
    const keep = new Set(data.nodes.map((n) => n.id));
    return {
      nodes: data.nodes.map((n) => ({
        id: n.id,
        name: n.label,
        type: n.type,
        community: n.communityId ?? null,
        val: 1 + Math.min(8, (n.evidenceCount ?? 1) + (deg.get(n.id) ?? 0) * 0.3),
        color: communityColor(n.communityId),
        raw: n,
      })),
      links: data.edges
        .filter((e) => keep.has(e.source) && keep.has(e.target))
        .map((e) => ({ source: e.source, target: e.target })),
    };
  }, [data]);

  return (
    <Suspense fallback={<div className="grid h-full place-items-center text-sm text-faint">Загрузка 3D…</div>}>
      <ForceGraph3D
        graphData={graph}
        backgroundColor="#14161a"
        nodeColor={(n: any) => n.color}
        nodeVal={(n: any) => n.val}
        nodeLabel={(n: any) =>
          `${n.name} · ${n.type}${n.community !== null ? ` · кластер #${n.community}` : ''}`
        }
        nodeOpacity={0.92}
        linkColor={() => '#39414d'}
        linkOpacity={0.22}
        linkWidth={0.5}
        enableNodeDrag={false}
        showNavInfo={false}
      />
    </Suspense>
  );
}

export function LiveGdsView() {
  const qc = useQueryClient();
  const [seed, setSeed] = useState('');

  const status = useQuery<GdsStatus>({ queryKey: ['gds-status'], queryFn: () => api.gdsStatus() });
  const available = status.data?.available;

  const graph = useQuery<GraphResponse>({
    queryKey: ['gds-colored-graph'],
    queryFn: () => api.gdsColoredGraph(400),
    enabled: available === true,
  });
  const communities = useQuery<CommunitiesResponse>({
    queryKey: ['gds-communities'],
    queryFn: () => api.gdsCommunities(24),
    enabled: available === true,
  });

  const seeds = useQuery({
    queryKey: ['gds-seeds'],
    queryFn: () => api.graphNodes('Material', 100),
    enabled: available === true,
  });
  const seedId = seed || seeds.data?.nodes?.[0]?.id || '';
  const similar = useQuery<SimilarResponse>({
    queryKey: ['gds-similar', seedId],
    queryFn: () => api.gdsSimilar(seedId, 10),
    enabled: available === true && !!seedId,
  });

  const runLouvain = useMutation({
    mutationFn: () => api.gdsLouvain(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gds-communities'] });
      qc.invalidateQueries({ queryKey: ['gds-colored-graph'] });
      qc.invalidateQueries({ queryKey: ['gds-status'] });
    },
  });

  if (status.isLoading) {
    return <div className="grid h-full place-items-center text-sm text-faint">Проверяем живой GDS…</div>;
  }

  if (available === false) {
    return (
      <div className="h-full overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-2xl">
          <div className="eyebrow mb-1">живой GDS · Neo4j · §3.14</div>
          <h2 className="mb-2 font-display text-2xl font-semibold">Louvain-сообщества на живом графе</h2>
          <div className="flex items-start gap-3 rounded-lg border border-line bg-surface/50 px-4 py-4 text-sm text-faint">
            <TriangleAlert size={18} className="mt-0.5 shrink-0 text-copper" />
            <div>
              Живой GDS доступен только на server-профиле (Neo4j + GDS-плагин).
              Сейчас активен профиль <span className="text-ink">{status.data?.profile}</span>.
              {status.data?.reason ? <div className="mt-1">{status.data.reason}</div> : null}
              <div className="mt-2">
                На embedded используйте эквивалент на NetworkX — панель «Сообщества» (§11).
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const result = runLouvain.data as LouvainResult | undefined;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="eyebrow mb-1">живой GDS · Neo4j · §3.14</div>
            <h2 className="font-display text-2xl font-semibold">Сообщества на живом графе</h2>
            <p className="mt-1 max-w-2xl text-sm text-faint">
              Настоящие <span className="text-ink">CALL gds.louvain</span> и{' '}
              <span className="text-ink">gds.nodeSimilarity</span> на боевом Neo4j: клубок
              раскрашен по кластерам-сообществам, панель показывает похожие материалы.
            </p>
          </div>
          <button
            onClick={() => runLouvain.mutate()}
            disabled={runLouvain.isPending}
            className="flex items-center gap-2 rounded-md border border-copper/40 bg-copper/15 px-4 py-2 text-sm font-medium text-copper transition hover:bg-copper/25 disabled:opacity-50"
          >
            {runLouvain.isPending ? <Wand2 size={15} className="animate-pulse" /> : <Play size={15} />}
            {runLouvain.isPending ? 'Считаем Louvain…' : 'Пересчитать Louvain'}
          </button>
        </div>
        {result && (
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-faint">
            <span>Сообществ: <span className="text-ink">{result.community_count}</span></span>
            <span>Модулярность: <span className="text-ink">{result.modularity}</span></span>
            <span>Узлов размечено: <span className="text-ink">{result.nodes_written}</span></span>
            <span>Проекция: <span className="text-ink">{result.projected.nodes}</span> узлов / {result.projected.relationships} рёбер</span>
          </div>
        )}
        {runLouvain.isError && (
          <div className="mt-2 flex items-center gap-2 text-xs text-copper">
            <TriangleAlert size={13} /> Не удалось запустить Louvain — проверьте GDS-плагин Neo4j.
          </div>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="relative min-h-0 flex-1 bg-graphite">
          {graph.isLoading && (
            <div className="grid h-full place-items-center text-sm text-faint">Строим клубок…</div>
          )}
          {graph.data && graph.data.nodes.length > 0 && <ColoredGraph data={graph.data} />}
          {graph.data && graph.data.nodes.length === 0 && (
            <div className="grid h-full place-items-center text-sm text-faint">
              Граф пуст — сначала загрузите корпус.
            </div>
          )}
        </div>

        <aside className="w-80 shrink-0 overflow-y-auto border-l border-line px-4 py-4">
          <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-faint">
            <Boxes size={13} /> Кластеры-сообщества
          </div>
          {communities.isLoading && <div className="text-sm text-faint">Читаем сообщества…</div>}
          {communities.data && !communities.data.clustered && (
            <div className="rounded-md border border-line bg-surface/40 px-3 py-3 text-xs text-faint">
              Граф ещё не кластеризован. Нажмите «Пересчитать Louvain».
            </div>
          )}
          <ul className="space-y-1.5">
            {communities.data?.communities.map((c) => (
              <li
                key={c.community_id}
                className="rounded-md border border-line bg-surface/40 px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 shrink-0 rounded-full"
                    style={{ backgroundColor: communityColor(c.community_id) }}
                  />
                  <span className="text-sm font-medium text-ink">Кластер #{c.community_id}</span>
                  <span className="ml-auto text-xs text-faint">{c.size}</span>
                </div>
                {c.top_entities.length > 0 && (
                  <div className="mt-1 truncate text-[11px] text-faint" title={c.top_entities.join(', ')}>
                    {c.top_entities.slice(0, 4).join(' · ')}
                  </div>
                )}
              </li>
            ))}
          </ul>

          <div className="mb-2 mt-6 flex items-center gap-2 text-[11px] uppercase tracking-wide text-faint">
            <Sparkles size={13} /> Похожие материалы · nodeSimilarity
          </div>
          <select
            value={seedId}
            onChange={(e) => setSeed(e.target.value)}
            className="mb-2 w-full rounded-md border border-line bg-surface/60 px-2 py-1.5 text-sm text-ink focus:border-copper/50 focus:outline-none"
          >
            {seeds.data?.nodes?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || s.id}
              </option>
            ))}
          </select>
          {similar.isLoading && <div className="text-xs text-faint">Ищем похожие…</div>}
          {similar.data && similar.data.count === 0 && (
            <div className="text-xs text-faint">Нет топологически похожих узлов.</div>
          )}
          <ul className="space-y-1.5">
            {similar.data?.similar.map((s) => (
              <li
                key={s.id}
                className="flex items-center gap-2 rounded-md border border-line bg-surface/40 px-3 py-2"
              >
                <Network size={13} className="shrink-0 text-copper" />
                <span className="min-w-0 flex-1 truncate text-sm text-ink" title={s.name}>
                  {s.name}
                </span>
                <span className="text-xs text-copper">{(s.similarity * 100).toFixed(0)}%</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}

export default LiveGdsView;
