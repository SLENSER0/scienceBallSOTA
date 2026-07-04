import { useMemo, useState } from 'react';
import {
  ArrowRight,
  Camera,
  GitCompareArrows,
  Loader2,
  Minus,
  Pencil,
  Plus,
  RotateCcw,
} from 'lucide-react';

// §14.6 «Визуальный diff графа до/после курирования».
// Self-contained (no api.ts edits): talks to the curation-graph-diff router
// directly with the same session-auth convention as api.ts. Flow:
//   1) снять снимок «ДО» вокруг seed-узлов (GET /snapshot),
//   2) куратор редактирует граф в модуле «Курирование»,
//   3) «Сравнить с текущим» (POST /) — сервер снимает живое «ПОСЛЕ» и вернёт дельту.

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

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

type Row = Record<string, unknown> & { id: string; _before?: Record<string, unknown>; _after?: Record<string, unknown> };

interface Snapshot {
  nodes: Row[];
  edges: Row[];
  seed_ids: string[];
  captured_at: string;
  counts: { nodes: number; edges: number };
  truncated: boolean;
}

interface GraphDelta {
  added_nodes: Row[];
  removed_nodes: Row[];
  changed_nodes: Row[];
  added_edges: Row[];
  removed_edges: Row[];
  changed_edges: Row[];
  added: number;
  removed: number;
  changed: number;
  summary: string;
  before_counts: { nodes: number; edges: number };
  after_counts: { nodes: number; edges: number };
  after_snapshot_meta?: { captured_at: string; seed_ids: string[]; truncated: boolean };
}

function nodeName(r: Row): string {
  return (r['prop:name'] as string) || (r.label as string) || r.id;
}

function nodeType(r: Row): string {
  return (r.type as string) || 'Entity';
}

function edgeLabel(r: Row): string {
  const s = (r.source as string) ?? '?';
  const t = (r.target as string) ?? '?';
  const rel = (r.label as string) || (r.type as string) || '—';
  return `${s} —[${rel}]→ ${t}`;
}

/** Список полей, реально изменившихся между _before и _after изменённой записи. */
function changedFields(r: Row): { key: string; before: unknown; after: unknown }[] {
  const before = r._before ?? {};
  const after = r._after ?? {};
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const out: { key: string; before: unknown; after: unknown }[] = [];
  for (const key of keys) {
    if (key === 'id') continue;
    const b = (before as Record<string, unknown>)[key];
    const a = (after as Record<string, unknown>)[key];
    if (JSON.stringify(b) !== JSON.stringify(a)) out.push({ key, before: b, after: a });
  }
  return out.sort((x, y) => x.key.localeCompare(y.key));
}

function fmtVal(v: unknown): string {
  if (v === undefined || v === null) return '∅';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function StatTile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="panel p-3">
      <div className="text-xs uppercase tracking-wide text-faint">{label}</div>
      <div className={`mt-1 font-display text-2xl ${tone}`}>{value}</div>
    </div>
  );
}

function Chip({ text, tone, sub }: { text: string; tone: string; sub?: string }) {
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs ${tone}`}
      title={sub}
    >
      <span className="truncate">{text}</span>
      {sub && <span className="shrink-0 font-mono text-[10px] opacity-70">{sub}</span>}
    </span>
  );
}

const GREEN = 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300';
const RED = 'border-red-500/40 bg-red-500/10 text-red-300';

function Section({
  title,
  icon,
  count,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  count: number;
  children: React.ReactNode;
}) {
  if (count === 0) return null;
  return (
    <div className="panel p-4">
      <h4 className="mb-3 flex items-center gap-2 font-display text-base">
        {icon} {title} <span className="text-faint">({count})</span>
      </h4>
      {children}
    </div>
  );
}

export function GraphDiffView() {
  const [nodeIds, setNodeIds] = useState('');
  const [expand, setExpand] = useState(1);
  const [before, setBefore] = useState<Snapshot | null>(null);
  const [diff, setDiff] = useState<GraphDelta | null>(null);
  const [busy, setBusy] = useState<'snapshot' | 'compare' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const seedParam = useMemo(
    () => nodeIds.split(',').map((s) => s.trim()).filter(Boolean),
    [nodeIds],
  );

  async function takeSnapshot() {
    setBusy('snapshot');
    setError(null);
    setDiff(null);
    try {
      const q = new URLSearchParams({ node_ids: seedParam.join(','), expand: String(expand) });
      const snap = await apiGet<Snapshot>(`/api/v1/graph/curation-diff/snapshot?${q}`);
      setBefore(snap);
      // если seed не вводили — подставим снятые id, чтобы «после» брал тот же подграф
      if (seedParam.length === 0 && snap.seed_ids.length) setNodeIds(snap.seed_ids.join(', '));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function compareLive() {
    if (!before) return;
    setBusy('compare');
    setError(null);
    try {
      const seeds = seedParam.length ? seedParam : before.seed_ids;
      const delta = await apiPost<GraphDelta>('/api/v1/graph/curation-diff', {
        before: { nodes: before.nodes, edges: before.edges },
        node_ids: seeds,
        expand,
      });
      setDiff(delta);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function reset() {
    setBefore(null);
    setDiff(null);
    setError(null);
  }

  const nodeTotal = diff ? diff.added_nodes.length + diff.removed_nodes.length + diff.changed_nodes.length : 0;
  const edgeTotal = diff ? diff.added_edges.length + diff.removed_edges.length + diff.changed_edges.length : 0;
  const noChanges = diff !== null && nodeTotal === 0 && edgeTotal === 0;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">граф · курирование · §14.6</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Визуальный diff графа</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Наглядно показывает эффект курирования: какие узлы и рёбра были добавлены, удалены или
          изменены между двумя версиями подграфа. Снимите снимок «ДО», отредактируйте граф в модуле
          «Курирование» (merge · edit · verify · mark-inferred), затем сравните с живым состоянием —
          дельта считается на сервере (Neo4j :8000) движком graph/diff.
        </p>

        {/* Controls */}
        <div className="panel mb-5 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex-1 min-w-[240px]">
              <span className="mb-1 block text-xs uppercase tracking-wide text-faint">
                Seed-узлы (id через запятую, пусто = выборка из графа)
              </span>
              <input
                value={nodeIds}
                onChange={(e) => setNodeIds(e.target.value)}
                placeholder="напр. mat:cu, prop:hardness"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
              />
            </label>
            <label>
              <span className="mb-1 block text-xs uppercase tracking-wide text-faint">Расширение (шагов)</span>
              <select
                value={expand}
                onChange={(e) => setExpand(Number(e.target.value))}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
              >
                {[0, 1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={takeSnapshot}
              disabled={busy !== null}
              className="inline-flex items-center gap-2 rounded-lg border border-copper/50 bg-copper/10 px-3 py-2 text-sm text-copper hover:bg-copper/20 disabled:opacity-50"
            >
              {busy === 'snapshot' ? <Loader2 size={15} className="animate-spin" /> : <Camera size={15} />}
              Снять снимок «ДО»
            </button>
            <button
              onClick={compareLive}
              disabled={busy !== null || !before}
              className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 text-sm text-ink hover:bg-white/[0.08] disabled:opacity-40"
            >
              {busy === 'compare' ? <Loader2 size={15} className="animate-spin" /> : <GitCompareArrows size={15} />}
              Сравнить с текущим
            </button>
            {(before || diff) && (
              <button
                onClick={reset}
                disabled={busy !== null}
                className="inline-flex items-center gap-2 rounded-lg px-2 py-2 text-sm text-faint hover:text-ink disabled:opacity-50"
              >
                <RotateCcw size={15} /> Сброс
              </button>
            )}
          </div>

          {before && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-faint">
              <Camera size={13} className="text-emerald-400" />
              Снимок «ДО»: <span className="text-ink">{before.counts.nodes} узлов · {before.counts.edges} рёбер</span>
              <span className="opacity-60">({new Date(before.captured_at).toLocaleString('ru-RU')})</span>
              {before.truncated && <span className="text-amber-400">⚠ усечён по лимиту</span>}
              <span className="ml-2">→ теперь отредактируйте граф и нажмите «Сравнить с текущим».</span>
            </div>
          )}
        </div>

        {error && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">Ошибка: {error}</div>
        )}

        {/* Diff result */}
        {diff && (
          <div className="space-y-4">
            <div className="panel p-3 text-sm text-ink">{diff.summary}</div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <StatTile label="Узлы +" value={diff.added_nodes.length} tone="text-emerald-400" />
              <StatTile label="Узлы −" value={diff.removed_nodes.length} tone="text-red-400" />
              <StatTile label="Узлы ~" value={diff.changed_nodes.length} tone="text-amber-400" />
              <StatTile label="Рёбра +" value={diff.added_edges.length} tone="text-emerald-400" />
              <StatTile label="Рёбра −" value={diff.removed_edges.length} tone="text-red-400" />
              <StatTile label="Рёбра ~" value={diff.changed_edges.length} tone="text-amber-400" />
            </div>

            {noChanges && (
              <div className="panel p-4 text-sm text-faint">
                Различий нет — подграф не изменился между снимком «ДО» и текущим состоянием.
              </div>
            )}

            <Section title="Добавленные узлы" icon={<Plus size={16} className="text-emerald-400" />} count={diff.added_nodes.length}>
              <div className="flex flex-wrap gap-2">
                {diff.added_nodes.map((n) => (
                  <Chip key={n.id} text={nodeName(n)} sub={nodeType(n)} tone={GREEN} />
                ))}
              </div>
            </Section>

            <Section title="Удалённые узлы" icon={<Minus size={16} className="text-red-400" />} count={diff.removed_nodes.length}>
              <div className="flex flex-wrap gap-2">
                {diff.removed_nodes.map((n) => (
                  <Chip key={n.id} text={nodeName(n)} sub={nodeType(n)} tone={RED} />
                ))}
              </div>
            </Section>

            <Section title="Изменённые узлы" icon={<Pencil size={16} className="text-amber-400" />} count={diff.changed_nodes.length}>
              <div className="space-y-3">
                {diff.changed_nodes.map((n) => (
                  <div key={n.id} className="rounded-lg border border-amber-500/25 bg-amber-500/[0.04] p-3">
                    <div className="mb-2 flex items-center gap-2 text-sm">
                      <span className="font-medium text-ink">{nodeName(n)}</span>
                      <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-faint">
                        {n.id}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {changedFields(n).map((f) => (
                        <div key={f.key} className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="font-mono text-faint">{f.key}</span>
                          <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-red-300 line-through">
                            {fmtVal(f.before)}
                          </span>
                          <ArrowRight size={12} className="text-faint" />
                          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300">
                            {fmtVal(f.after)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            <Section title="Добавленные рёбра" icon={<Plus size={16} className="text-emerald-400" />} count={diff.added_edges.length}>
              <div className="flex flex-col gap-1.5">
                {diff.added_edges.map((e) => (
                  <Chip key={e.id} text={edgeLabel(e)} tone={GREEN} />
                ))}
              </div>
            </Section>

            <Section title="Удалённые рёбра" icon={<Minus size={16} className="text-red-400" />} count={diff.removed_edges.length}>
              <div className="flex flex-col gap-1.5">
                {diff.removed_edges.map((e) => (
                  <Chip key={e.id} text={edgeLabel(e)} tone={RED} />
                ))}
              </div>
            </Section>

            <Section title="Изменённые рёбра" icon={<Pencil size={16} className="text-amber-400" />} count={diff.changed_edges.length}>
              <div className="space-y-3">
                {diff.changed_edges.map((e) => (
                  <div key={e.id} className="rounded-lg border border-amber-500/25 bg-amber-500/[0.04] p-3">
                    <div className="mb-2 font-mono text-xs text-ink">{edgeLabel(e)}</div>
                    <div className="space-y-1">
                      {changedFields(e).map((f) => (
                        <div key={f.key} className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="font-mono text-faint">{f.key}</span>
                          <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-red-300 line-through">
                            {fmtVal(f.before)}
                          </span>
                          <ArrowRight size={12} className="text-faint" />
                          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300">
                            {fmtVal(f.after)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          </div>
        )}

        {!before && !diff && !error && (
          <div className="panel p-6 text-center text-sm text-faint">
            Начните со снимка «ДО»: оставьте поле seed пустым для автоматической выборки подграфа или
            укажите конкретные id узлов.
          </div>
        )}
      </div>
    </div>
  );
}
