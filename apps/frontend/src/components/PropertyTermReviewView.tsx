import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  Loader2,
  Play,
  Ruler,
  Sparkles,
  Tag,
} from 'lucide-react';

// §8.6 Эмиссия new_property_term (schema_change) в очередь ревью при неизвестном
// свойстве. Self-contained (без правок api.ts): дёргает роутер
// /api/v1/schema/property-terms/* напрямую с той же session-auth конвенцией.

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

interface MentionInput {
  mention: string;
  unit: string | null;
}

interface MentionResult {
  mention: string;
  unit: string | null;
  canonical_id: string | null;
  score: number;
  status: string;
  unit_ok: boolean;
  flags: string[];
  review_needed: boolean;
}

interface EmittedTask {
  task_id: string;
  dedup_key: string;
  kind: string;
  priority: number;
  target_id: string;
  flags: string[];
  payload: {
    term: string;
    unit: string | null;
    nearest: string | null;
    score: number;
    occurrences: number;
  };
}

interface MapResponse {
  count: number;
  emitted: number;
  persisted: boolean;
  min_sim: number;
  results: MentionResult[];
  tasks: EmittedTask[];
}

interface PendingTask {
  task_id: string;
  target_id: string;
  kind: string;
  priority: number;
  status: string;
  created_at: string;
}
interface PendingResponse {
  kind: string;
  count: number;
  status_counts: Record<string, number>;
  tasks: PendingTask[];
}

interface VocabResponse {
  term_count: number;
  min_sim: number;
  reason: string;
  sample_canonical_ids: string[];
}

const DEFAULT_INPUT = `hardness
Vickers hardness | HV
HV
unobtanium modulus
tensile strength | MPa`;

function parseInput(raw: string): MentionInput[] {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const [mention, unit] = line.split('|').map((s) => s.trim());
      return { mention, unit: unit || null };
    });
}

function StatusBadge({ r }: { r: MentionResult }) {
  if (r.review_needed) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 px-2 py-0.5 text-xs font-medium text-emerald-400">
        <Sparkles size={12} /> new_property_term
      </span>
    );
  }
  if (r.flags.includes('unit_mismatch')) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 px-2 py-0.5 text-xs font-medium text-amber-400">
        <Ruler size={12} /> unit_mismatch
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-sky-500/40 px-2 py-0.5 text-xs font-medium text-sky-400">
      <CheckCircle2 size={12} /> mapped
    </span>
  );
}

export function PropertyTermReviewView() {
  const [input, setInput] = useState(DEFAULT_INPUT);
  const [minSim, setMinSim] = useState(0.82);
  const [persist, setPersist] = useState(true);
  const [result, setResult] = useState<MapResponse | null>(null);

  const vocab = useQuery({
    queryKey: ['prop-term-vocab'],
    queryFn: () => apiGet<VocabResponse>('/api/v1/schema/property-terms/vocab'),
  });

  const pending = useQuery({
    queryKey: ['prop-term-pending'],
    queryFn: () => apiGet<PendingResponse>('/api/v1/schema/property-terms/pending?limit=50'),
  });

  const map = useMutation({
    mutationFn: () =>
      apiPost<MapResponse>('/api/v1/schema/property-terms/map', {
        mentions: parseInput(input),
        min_sim: minSim,
        persist,
      }),
    onSuccess: (data) => {
      setResult(data);
      if (persist) pending.refetch();
    },
  });

  const mapped = useMemo(
    () => (result ? result.results.filter((r) => !r.review_needed && r.flags.length === 0).length : 0),
    [result],
  );

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
          <BookOpenCheck size={20} className="text-emerald-400" />
          Эмиссия new_property_term (§8.6)
        </h1>
        <p className="max-w-3xl text-sm text-faint">
          Неизвестный property-термин прогоняется через каскадный маппер (точный/синоним →
          fuzzy → порог). Ниже порога — событие <code className="text-emerald-400">schema_change</code>{' '}
          с причиной <code className="text-emerald-400">new_property_term</code>, персистируемое в
          очередь ревью (§16.5) с дедупликацией. Несовместимая единица даёт флаг{' '}
          <code className="text-amber-400">unit_mismatch</code>.
        </p>
        {vocab.data && (
          <p className="text-xs text-faint">
            Словарь: <span className="font-mono text-ink/80">{vocab.data.term_count}</span> canonical-свойств ·
            порог по умолчанию <span className="font-mono text-ink/80">{vocab.data.min_sim}</span>
          </p>
        )}
      </header>

      <section className="rounded-xl border border-white/10 bg-black/20 p-4">
        <label className="mb-2 block text-sm font-medium text-ink">
          Property-упоминания (по одному в строке, опц. <code>| unit</code>)
        </label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={6}
          spellCheck={false}
          className="w-full resize-y rounded-lg border border-white/10 bg-black/30 p-3 font-mono text-sm text-ink outline-none focus:border-emerald-500/50"
        />
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-faint">
            min_sim
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={minSim}
              onChange={(e) => setMinSim(Number(e.target.value))}
            />
            <span className="w-10 font-mono text-ink/80">{minSim.toFixed(2)}</span>
          </label>
          <label className="flex items-center gap-2 text-sm text-faint">
            <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
            персистить в очередь
          </label>
          <button
            onClick={() => map.mutate()}
            disabled={map.isPending}
            className="ml-auto inline-flex items-center gap-2 rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400 disabled:opacity-50"
          >
            {map.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            Сопоставить
          </button>
        </div>
        {map.isError && (
          <p className="mt-2 flex items-center gap-2 text-sm text-red-400">
            <AlertTriangle size={14} /> {String((map.error as Error).message)}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-3">
          <div className="flex flex-wrap gap-3 text-sm">
            <span className="rounded-lg border border-white/10 px-3 py-1 text-faint">
              всего: <span className="font-mono text-ink">{result.count}</span>
            </span>
            <span className="rounded-lg border border-sky-500/30 px-3 py-1 text-sky-400">
              mapped: <span className="font-mono">{mapped}</span>
            </span>
            <span className="rounded-lg border border-emerald-500/30 px-3 py-1 text-emerald-400">
              эмитировано: <span className="font-mono">{result.emitted}</span>
            </span>
            <span className="rounded-lg border border-white/10 px-3 py-1 text-faint">
              {result.persisted ? 'персистировано в очередь' : 'dry-run (не персистировано)'}
            </span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/5 text-xs uppercase text-faint">
                <tr>
                  <th className="px-3 py-2">Термин</th>
                  <th className="px-3 py-2">Unit</th>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2">Ближайший canonical</th>
                  <th className="px-3 py-2">Score</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="px-3 py-2 font-mono text-ink">{r.mention}</td>
                    <td className="px-3 py-2 text-faint">{r.unit ?? '—'}</td>
                    <td className="px-3 py-2">
                      <StatusBadge r={r} />
                    </td>
                    <td className="px-3 py-2 font-mono text-ink/70">{r.canonical_id ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-ink/70">{r.score.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Tag size={16} className="text-emerald-400" />
          Очередь: новые термины схемы ({pending.data?.count ?? 0})
        </h2>
        {pending.isLoading ? (
          <p className="text-sm text-faint">Загрузка…</p>
        ) : pending.data && pending.data.tasks.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/5 text-xs uppercase text-faint">
                <tr>
                  <th className="px-3 py-2">target_id</th>
                  <th className="px-3 py-2">Приоритет</th>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2">Создано</th>
                </tr>
              </thead>
              <tbody>
                {pending.data.tasks.map((t) => (
                  <tr key={t.task_id} className="border-t border-white/5">
                    <td className="px-3 py-2 font-mono text-ink/80">{t.target_id}</td>
                    <td className="px-3 py-2 font-mono text-ink/70">{t.priority.toFixed(3)}</td>
                    <td className="px-3 py-2 text-faint">{t.status}</td>
                    <td className="px-3 py-2 text-faint">{t.created_at.slice(0, 19).replace('T', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-faint">Открытых задач new_property_term нет.</p>
        )}
      </section>
    </div>
  );
}
