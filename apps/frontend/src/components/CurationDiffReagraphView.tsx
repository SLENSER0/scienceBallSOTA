import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  GitCompareArrows,
  Loader2,
  Plus,
  Minus,
  Pencil,
  ArrowRight,
  User,
  Clock,
  Filter,
  AlertTriangle,
} from 'lucide-react';

// §16.10 «Graph diff до/после курирования». Self-contained (no api.ts edits): it
// calls the curation-diff-reagraph router directly with the same session-auth
// convention as api.ts. The diff is built server-side from CurationEvent records,
// so everything shown is a curation change — ingestion edits are excluded.

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

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

type Status = 'added' | 'removed' | 'changed';

interface DiffNode {
  id: string;
  status: Status;
  label?: string | null;
  name: string;
  data: {
    changes?: Record<string, [unknown, unknown]>;
    [k: string]: unknown;
  };
}
interface DiffEdge {
  id: string;
  status: Status;
  data: Record<string, unknown>;
}
interface Counts {
  added_nodes: number;
  removed_nodes: number;
  changed_nodes: number;
  added_edges: number;
  removed_edges: number;
}
interface AuditEvent {
  event_id: string;
  action: string | null;
  actor: string | null;
  target_id: string;
  reason: string;
  created_at: string;
}
interface ReagraphResponse {
  nodes: DiffNode[];
  edges: DiffEdge[];
  counts: Counts;
  events: AuditEvent[];
  window: { since: string | null; until: string | null; actor: string | null; action: string | null };
  curated_targets: number;
  event_count: number;
}

const STATUS_META: Record<
  Status,
  { ru: string; ring: string; text: string; bg: string; icon: typeof Plus }
> = {
  added: {
    ru: 'Добавлено',
    ring: 'border-emerald-500/40',
    text: 'text-emerald-400',
    bg: 'bg-emerald-500/10',
    icon: Plus,
  },
  removed: {
    ru: 'Удалено',
    ring: 'border-red-500/40',
    text: 'text-red-400',
    bg: 'bg-red-500/10',
    icon: Minus,
  },
  changed: {
    ru: 'Изменено',
    ring: 'border-amber-500/40',
    text: 'text-amber-400',
    bg: 'bg-amber-500/10',
    icon: Pencil,
  },
};

// Curation actions the backend records (§12.2 / kg_schema.enums.CurationAction).
const ACTION_OPTIONS = [
  '',
  'correct',
  'accept',
  'reject',
  'merge',
  'split',
  'alias_add',
  'mark_inferred',
  'manual_evidence',
  'annotate',
  'resolve_contradiction',
];

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '∅';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function fmtTime(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU');
}

function StatChip({ status, n }: { status: Status; n: number }) {
  const m = STATUS_META[status];
  const Icon = m.icon;
  return (
    <div className={`flex items-center gap-2 rounded-lg border ${m.ring} ${m.bg} px-3 py-2`}>
      <Icon size={15} className={m.text} />
      <span className={`text-lg font-semibold ${m.text}`}>{n}</span>
      <span className="text-xs text-slate-400">{m.ru}</span>
    </div>
  );
}

function ChangedRow({ field, before, after }: { field: string; before: unknown; after: unknown }) {
  return (
    <div className="grid grid-cols-[minmax(90px,auto)_1fr] gap-x-3 gap-y-0.5 py-1 text-xs">
      <span className="font-mono text-slate-400">{field}</span>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-red-500/10 px-1.5 py-0.5 font-mono text-red-300 line-through">
          {fmtVal(before)}
        </span>
        <ArrowRight size={12} className="text-slate-500" />
        <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-emerald-300">
          {fmtVal(after)}
        </span>
      </div>
    </div>
  );
}

function NodeCard({ node }: { node: DiffNode }) {
  const m = STATUS_META[node.status];
  const Icon = m.icon;
  const changes = node.data?.changes;
  const propKeys =
    node.status === 'changed'
      ? []
      : Object.keys(node.data || {}).filter((k) => k !== 'name' && k !== 'label');
  return (
    <div className={`rounded-lg border ${m.ring} bg-slate-900/40 p-3`}>
      <div className="flex items-center gap-2">
        <Icon size={14} className={m.text} />
        <span className="truncate text-sm font-medium text-slate-100">{node.name}</span>
        {node.label && (
          <span className="rounded bg-slate-700/60 px-1.5 py-0.5 text-[10px] text-slate-300">
            {node.label}
          </span>
        )}
        <span className={`ml-auto text-[10px] ${m.text}`}>{m.ru}</span>
      </div>
      <div className="mt-0.5 truncate font-mono text-[10px] text-slate-500">{node.id}</div>

      {node.status === 'changed' && changes && (
        <div className="mt-2 border-t border-slate-700/50 pt-1">
          {Object.entries(changes).map(([field, [before, after]]) => (
            <ChangedRow key={field} field={field} before={before} after={after} />
          ))}
        </div>
      )}

      {node.status !== 'changed' && propKeys.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1 border-t border-slate-700/50 pt-2">
          {propKeys.slice(0, 8).map((k) => (
            <span
              key={k}
              className="rounded bg-slate-800/70 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
            >
              {k}={fmtVal(node.data[k])}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function CurationDiffReagraphView() {
  const [action, setAction] = useState('');
  const [actor, setActor] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [applied, setApplied] = useState(0);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    if (action) p.set('action', action);
    if (actor.trim()) p.set('actor', actor.trim());
    if (since) p.set('since', new Date(since).toISOString());
    if (until) p.set('until', new Date(until).toISOString());
    return p.toString();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applied]);

  const { data, isLoading, error, refetch, isFetching } = useQuery<ReagraphResponse>({
    queryKey: ['curation-diff-reagraph', qs],
    queryFn: () => apiGet(`/api/v1/curation-diff-reagraph/reagraph${qs ? `?${qs}` : ''}`),
  });

  const nodesByStatus = useMemo(() => {
    const g: Record<Status, DiffNode[]> = { added: [], removed: [], changed: [] };
    for (const n of data?.nodes ?? []) g[n.status]?.push(n);
    return g;
  }, [data]);

  const totalNodes = data?.nodes.length ?? 0;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <header className="flex flex-wrap items-center gap-3">
        <GitCompareArrows className="text-cyan-400" size={22} />
        <div>
          <h1 className="text-lg font-semibold text-slate-100">
            Что изменилось при курировании
          </h1>
          <p className="text-xs text-slate-400">
            Показаны только правки, сделанные при курировании: что добавлено, удалено и изменено — с прежним и новым значением.
          </p>
        </div>
        {(isFetching || isLoading) && <Loader2 className="animate-spin text-slate-500" size={16} />}
      </header>

      {/* filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-700/50 bg-slate-900/30 p-3">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Filter size={13} /> Фильтры
        </div>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-400">
          Действие
          <select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
          >
            {ACTION_OPTIONS.map((a) => (
              <option key={a} value={a}>
                {a || 'все'}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-400">
          Куратор
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="напр. curator"
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-400">
          С даты
          <input
            type="datetime-local"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] text-slate-400">
          По дату
          <input
            type="datetime-local"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
          />
        </label>
        <button
          onClick={() => {
            setApplied((n) => n + 1);
            setTimeout(() => refetch(), 0);
          }}
          className="rounded bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500"
        >
          Применить
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
          <AlertTriangle size={16} /> Ошибка загрузки изменений: {String((error as Error).message)}
        </div>
      )}

      {/* counts */}
      {data && (
        <div className="flex flex-wrap items-center gap-3">
          <StatChip status="added" n={data.counts.added_nodes} />
          <StatChip status="removed" n={data.counts.removed_nodes} />
          <StatChip status="changed" n={data.counts.changed_nodes} />
          <div className="ml-auto text-xs text-slate-500">
            {data.curated_targets} курируемых узлов · {data.event_count} событий
          </div>
        </div>
      )}

      {data && totalNodes === 0 && !isLoading && (
        <div className="rounded-lg border border-slate-700/50 bg-slate-900/30 p-6 text-center text-sm text-slate-400">
          За выбранный период правок курирования нет. Утвердите, объедините или исправьте что-нибудь в очереди курирования — изменения появятся здесь.
        </div>
      )}

      {/* diff + audit */}
      {data && totalNodes > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          {/* node diff columns */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {(['changed', 'added', 'removed'] as Status[]).map((st) => {
              const m = STATUS_META[st];
              const list = nodesByStatus[st];
              return (
                <div key={st} className="flex flex-col gap-2">
                  <div className={`flex items-center gap-2 text-sm font-medium ${m.text}`}>
                    {m.ru} <span className="text-slate-500">({list.length})</span>
                  </div>
                  {list.length === 0 && (
                    <div className="rounded border border-dashed border-slate-700/60 p-3 text-center text-[11px] text-slate-600">
                      —
                    </div>
                  )}
                  {list.map((n) => (
                    <NodeCard key={n.id} node={n} />
                  ))}
                </div>
              );
            })}
          </div>

          {/* audit trail */}
          <div className="flex flex-col gap-2">
            <div className="text-sm font-medium text-slate-300">
              Аудит курирования <span className="text-slate-500">({data.events.length})</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {data.events.map((e) => (
                <div
                  key={e.event_id}
                  className="rounded border border-slate-700/50 bg-slate-900/40 p-2 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 font-medium text-cyan-300">
                      {e.action ?? '—'}
                    </span>
                    <span className="flex items-center gap-1 text-slate-400">
                      <User size={11} /> {e.actor ?? '—'}
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-slate-500">
                      <Clock size={11} /> {fmtTime(e.created_at)}
                    </span>
                  </div>
                  <div className="mt-1 truncate font-mono text-[10px] text-slate-500">
                    {e.target_id}
                  </div>
                  {e.reason && <div className="mt-0.5 text-slate-400">{e.reason}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CurationDiffReagraphView;
