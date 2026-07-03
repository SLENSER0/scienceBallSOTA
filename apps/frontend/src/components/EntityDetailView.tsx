import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Boxes, Loader2, Network as NetworkIcon } from 'lucide-react';
import { api } from '../api';
import type { GraphNode } from '../types';
import { GraphPanel } from './GraphPanel';

// Экран Entity Detail Page (§17.11 / §5.2.4): browse the graph's entities by type,
// then inspect one — its properties, a 1-hop neighbourhood graph (2D/3D), and its
// curation history. Powered by /graph/nodes, /entities/{id}/neighbors, /history.

const TYPES = [
  { label: 'TechnologySolution', ru: 'Технологии' },
  { label: 'Material', ru: 'Материалы' },
  { label: 'ProcessingRegime', ru: 'Режимы' },
  { label: 'Equipment', ru: 'Оборудование' },
  { label: 'Property', ru: 'Свойства' },
  { label: 'Gap', ru: 'Пробелы' },
  { label: 'Contradiction', ru: 'Противоречия' },
  { label: 'Paper', ru: 'Публикации' },
];

export function EntityDetailView() {
  const [type, setType] = useState('TechnologySolution');
  const [selId, setSelId] = useState<string | null>(null);

  const nodes = useQuery({ queryKey: ['nodes', type], queryFn: () => api.graphNodes(type, 60) });
  const list = nodes.data?.nodes ?? [];

  // Auto-select the first node when the list (re)loads and nothing valid is selected.
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

      {/* Right: detail */}
      <section className="min-h-0 overflow-y-auto">
        {selId ? <EntityDetail id={selId} /> : <Empty />}
      </section>
    </div>
  );
}

function EntityDetail({ id }: { id: string }) {
  const neigh = useQuery({ queryKey: ['ent-neighbors', id], queryFn: () => api.neighbors(id, 1) });
  const hist = useQuery({ queryKey: ['ent-history', id], queryFn: () => api.entityHistory(id) });

  const graph = neigh.data;
  const self: GraphNode | undefined = graph?.nodes.find((n) => n.id === id);
  const props = (self?.properties ?? {}) as Record<string, unknown>;

  return (
    <div className="p-6">
      <div className="eyebrow mb-1">{self?.type ?? 'Сущность'}</div>
      <h1 className="font-display text-xl font-semibold tracking-tight">{self?.label ?? id}</h1>
      <div className="mt-0.5 font-mono text-[10px] text-faint">{id}</div>

      {/* Property grid */}
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {Object.entries(props)
          .filter(([, v]) => v !== null && v !== '' && typeof v !== 'object')
          .slice(0, 12)
          .map(([k, v]) => (
            <div key={k} className="rounded-md border border-line bg-surface/40 px-3 py-2">
              <div className="font-mono text-[10px] uppercase tracking-wide text-faint">{k}</div>
              <div className="text-sm text-ink">{String(v)}</div>
            </div>
          ))}
      </div>

      {/* Neighbourhood graph */}
      <div className="mt-5">
        <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
          <NetworkIcon size={12} /> связи · {graph ? graph.nodes.length : 0} узлов
        </div>
        <div className="h-[380px] overflow-hidden rounded-md border border-line">
          {neigh.isLoading ? (
            <div className="flex h-full items-center justify-center font-mono text-xs text-faint">
              <Loader2 size={14} className="mr-2 animate-spin text-copper" /> строим граф…
            </div>
          ) : graph && graph.nodes.length > 0 ? (
            <GraphPanel data={graph} selectedId={id} />
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-xs text-faint">
              нет связей
            </div>
          )}
        </div>
      </div>

      {/* History */}
      {(hist.data?.history.length ?? 0) > 0 && (
        <div className="mt-5">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
            история изменений
          </div>
          <ul className="space-y-1">
            {hist.data!.history.map((r, i) => (
              <li key={i} className="font-mono text-[11px] text-muted">
                {JSON.stringify(r)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-full items-center justify-center text-center">
      <div>
        <Boxes size={30} className="mx-auto mb-2 text-faint" />
        <div className="font-mono text-xs text-faint">выберите сущность слева</div>
      </div>
    </div>
  );
}
