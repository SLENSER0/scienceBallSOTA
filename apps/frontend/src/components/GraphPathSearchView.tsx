import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Route, Spline, TriangleAlert, Waypoints } from 'lucide-react';
import { api } from '../api';

// §17.8 Path search Material↔Property с подсветкой пути. «Через ЧТО материал
// связан со свойством?» — выбираем источник и цель, backend перечисляет
// реляционные пути и помечает лучший флагом onPath; здесь рисуем найденный путь
// как читаемую цепочку узлов и типов связей, а альтернативы — списком.

export interface PathEndpoint {
  id: string;
  name: string;
  type: string;
}

export interface FoundPath {
  nodeIds: string[];
  nodeNames: string[];
  edgeIds: string[];
  relTypes: string[];
  length: number;
  reliability: number;
  linear: string;
  complete: boolean;
}

export interface PathSearchResult {
  found: boolean;
  detail?: string;
  source: PathEndpoint;
  target: PathEndpoint;
  maxHops: number;
  count: number;
  truncated?: boolean;
  paths: FoundPath[];
  graph: { nodes: unknown[]; edges: unknown[] };
  best: { nodeIds: string[]; edgeIds: string[]; missingSegments: number[][]; length: number } | null;
}

const HOPS = [2, 3, 4, 5, 6];

/** Одна цепочка пути: чипы узлов, разделённые типом связи. */
function PathChain({ path, highlight }: { path: FoundPath; highlight: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {path.nodeNames.map((name, i) => (
        <span key={`${name}-${i}`} className="flex items-center gap-1.5">
          <span
            className={
              'rounded-md border px-2 py-1 text-sm ' +
              (highlight
                ? 'border-copper/60 bg-copper/10 text-ink'
                : 'border-line bg-surface/60 text-ink')
            }
          >
            {name}
          </span>
          {i < path.relTypes.length && (
            <span className="flex items-center gap-1 font-mono text-[10px] text-faint">
              <ArrowRight size={12} className={highlight ? 'text-copper' : 'text-faint'} />
              {path.relTypes[i]}
              <ArrowRight size={12} className={highlight ? 'text-copper' : 'text-faint'} />
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

export function GraphPathSearchView() {
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [maxHops, setMaxHops] = useState(4);

  const sources = useQuery({
    queryKey: ['gp-endpoints', 'Material'],
    queryFn: () => api.graphPathEndpoints('Material'),
  });
  const targets = useQuery({
    queryKey: ['gp-endpoints', 'Property'],
    queryFn: () => api.graphPathEndpoints('Property'),
  });

  const src = sourceId || sources.data?.nodes[0]?.id || '';
  const dst = targetId || targets.data?.nodes[0]?.id || '';

  const res = useQuery({
    queryKey: ['gp-search', src, dst, maxHops],
    queryFn: () => api.graphPathSearch(src, dst, maxHops),
    enabled: !!src && !!dst && src !== dst,
  });

  const data = res.data;
  const best = data?.paths[0];
  const alternatives = useMemo(() => data?.paths.slice(1) ?? [], [data]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">связи в графе</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Путь между сущностями</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          Через ЧТО материал связан со свойством? Выберите источник и цель — система найдёт
          пути связей и подсветит лучший: цепочку узлов и типов связей от материала до
          свойства.
        </p>

        <div className="mb-5 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Материал (источник)</span>
            <select
              value={src}
              onChange={(e) => setSourceId(e.target.value)}
              className="min-w-64 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {sources.data?.nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Свойство (цель)</span>
            <select
              value={dst}
              onChange={(e) => setTargetId(e.target.value)}
              className="min-w-64 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {targets.data?.nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Макс. рёбер</span>
            <select
              value={maxHops}
              onChange={(e) => setMaxHops(Number(e.target.value))}
              className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {HOPS.map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </label>
        </div>

        {src === dst && src && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            Источник и цель совпадают — выберите разные сущности.
          </div>
        )}

        {res.isLoading && <div className="text-sm text-faint">Граф ищет путь…</div>}
        {res.isError && (
          <div className="flex items-center gap-2 text-sm text-copper">
            <TriangleAlert size={15} /> Не удалось выполнить поиск пути.
          </div>
        )}

        {data && !data.found && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            Путь не найден за {data.maxHops} рёбер.
            {data.detail === 'target unreachable within max_hops' && ' Попробуйте увеличить лимит рёбер.'}
          </div>
        )}

        {data && data.found && best && (
          <>
            <div className="mb-4 rounded-lg border border-copper/40 bg-copper/5 px-4 py-4">
              <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-copper">
                <Route size={13} /> Лучший путь · {best.length}{' '}
                {best.length === 1 ? 'ребро' : 'рёбер'} · надёжность{' '}
                {Math.round(best.reliability * 100)}%
              </div>
              <PathChain path={best} highlight />
              <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[10px] text-faint/80">
                <span>узлов в подграфе: {data.graph.nodes.length}</span>
                <span>рёбер: {data.graph.edges.length}</span>
                <span>рёбер в пути: {data.best?.edgeIds.length ?? 0}</span>
              </div>
            </div>

            {alternatives.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-faint">
                  <Spline size={13} /> Альтернативные пути ({alternatives.length})
                </div>
                <ul className="space-y-2">
                  {alternatives.map((p, i) => (
                    <li
                      key={p.linear + i}
                      className="rounded-lg border border-line bg-surface/50 px-4 py-3 transition hover:border-copper/40"
                    >
                      <div className="mb-2 flex items-center justify-between gap-3 font-mono text-[10px] text-faint">
                        <span>
                          {p.length} {p.length === 1 ? 'ребро' : 'рёбер'}
                        </span>
                        <span className="text-nickel-bright">
                          {Math.round(p.reliability * 100)}%
                        </span>
                      </div>
                      <PathChain path={p} highlight={false} />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4 flex items-center gap-1.5 text-[11px] text-faint">
              <Waypoints size={12} className="text-copper" /> {data.count} путей от «{data.source.name}»
              до «{data.target.name}»{data.truncated ? ' (показаны не все)' : ''}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
