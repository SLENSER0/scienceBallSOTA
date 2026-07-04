import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  BadgeCheck,
  Crown,
  FileText,
  Layers,
  Loader2,
  Search,
  Sparkles,
} from 'lucide-react';

// §12.4 — Ranking explainability: decompose fused component_scores in the UI.
// component_scores (dense / sparse / bm25 / graph_proximity / evidence_quality)
// are computed in the retrieval pipeline but hidden behind one opaque score;
// this "почему тут" panel exposes the fusion breakdown per hit.
//
// Self-contained (no api.ts edits): calls /api/v1/ranking/* directly with the
// same session-auth convention as api.ts / RerankLiveView.

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

// The five fusion signals (§10.2). Fixed order + colour so bars stay stable.
const SIGNAL_ORDER = [
  'dense',
  'sparse',
  'bm25',
  'graph_proximity',
  'evidence_quality',
] as const;
type SignalId = (typeof SIGNAL_ORDER)[number];

const SIGNAL_COLOR: Record<SignalId, string> = {
  dense: '#38bdf8', // sky
  sparse: '#a78bfa', // violet
  bm25: '#f59e0b', // amber
  graph_proximity: '#34d399', // emerald
  evidence_quality: '#f472b6', // pink
};

interface SignalMeta {
  id: string;
  weight: number;
  label: string;
  desc: string;
}
interface ExplainHit {
  id: string;
  name: string | null;
  type: string | null;
  domain: string | null;
  doc_id: string | null;
  score: number;
  component_scores: Record<string, number>;
  contributions: Record<string, number>;
  shares: Record<string, number>;
  dominant: string;
  review_status: string | null;
  verified: boolean | null;
}
interface ExplainResponse {
  query: string;
  count: number;
  weights: Record<string, number>;
  active_signals: string[];
  dense_available: boolean;
  signals: SignalMeta[];
  hits: ExplainHit[];
}
interface SignalsResponse {
  weights: Record<string, number>;
  weight_sum: number;
  signals: SignalMeta[];
}

function fmt(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '');
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '0%';
  return `${Math.round(v * 100)}%`;
}

function labelFor(signals: SignalMeta[], id: string): string {
  return signals.find((s) => s.id === id)?.label ?? id;
}

// Stacked bar: each signal's share of the fused total, coloured per signal.
function ShareBar({ shares }: { shares: Record<string, number> }) {
  const segs = SIGNAL_ORDER.map((s) => ({ s, v: shares[s] ?? 0 })).filter((x) => x.v > 0.0001);
  const total = segs.reduce((a, b) => a + b.v, 0) || 1;
  return (
    <div className="flex h-3 w-full overflow-hidden rounded bg-black/25">
      {segs.map(({ s, v }) => (
        <div
          key={s}
          style={{ width: `${(v / total) * 100}%`, backgroundColor: SIGNAL_COLOR[s] }}
          title={`${s}: ${pct(v)} вклада`}
        />
      ))}
    </div>
  );
}

function Legend({ signals }: { signals: SignalMeta[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11px]">
      {SIGNAL_ORDER.map((s) => {
        const meta = signals.find((m) => m.id === s);
        return (
          <span
            key={s}
            className="inline-flex items-center gap-1.5 text-faint"
            title={meta?.desc ?? ''}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: SIGNAL_COLOR[s] }}
            />
            {meta?.label ?? s}
            {meta ? <code className="text-ink">w={fmt(meta.weight, 2)}</code> : null}
          </span>
        );
      })}
    </div>
  );
}

function HitCard({ hit, signals }: { hit: ExplainHit; signals: SignalMeta[] }) {
  const [open, setOpen] = useState(false);
  const domColor = SIGNAL_COLOR[hit.dominant as SignalId] ?? '#94a3b8';
  return (
    <div className="panel p-3">
      <div className="flex items-baseline gap-2">
        <span className="flex-1 truncate text-sm font-medium text-ink" title={hit.name ?? hit.id}>
          {hit.name ?? hit.id}
        </span>
        {hit.verified && (
          <span
            className="inline-flex items-center gap-0.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] text-emerald-400"
            title="verified"
          >
            <BadgeCheck size={11} />
          </span>
        )}
        <span className="text-xs text-faint" title="fused score">
          {fmt(hit.score, 4)}
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
        {hit.type && <span className="rounded bg-black/20 px-1.5 py-0.5 text-faint">{hit.type}</span>}
        {hit.domain && (
          <span className="rounded bg-black/20 px-1.5 py-0.5 text-faint">{hit.domain}</span>
        )}
        {hit.doc_id && (
          <span
            className="inline-flex items-center gap-0.5 rounded bg-black/20 px-1.5 py-0.5 text-faint"
            title={hit.doc_id}
          >
            <FileText size={10} /> {hit.doc_id.slice(0, 10)}
          </span>
        )}
        <span
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium"
          style={{ backgroundColor: `${domColor}22`, color: domColor }}
          title="сигнал с максимальным вкладом в fused-оценку"
        >
          <Crown size={11} /> {labelFor(signals, hit.dominant)}
        </span>
      </div>

      <div className="mt-2">
        <ShareBar shares={hit.shares} />
      </div>

      <button
        onClick={() => setOpen((o) => !o)}
        className="mt-2 text-[11px] text-copper hover:underline"
      >
        {open ? 'Скрыть раскладку' : 'Почему тут? — раскладка сигналов'}
      </button>

      {open && (
        <table className="mt-2 w-full text-[11px]">
          <thead>
            <tr className="text-left text-faint">
              <th className="py-1 pr-2 font-normal">сигнал</th>
              <th className="py-1 pr-2 text-right font-normal">норм. score</th>
              <th className="py-1 pr-2 text-right font-normal">× вес</th>
              <th className="py-1 pr-2 text-right font-normal">вклад</th>
              <th className="py-1 text-right font-normal">доля</th>
            </tr>
          </thead>
          <tbody>
            {SIGNAL_ORDER.map((s) => {
              const meta = signals.find((m) => m.id === s);
              const comp = hit.component_scores[s];
              const contrib = hit.contributions[s] ?? 0;
              const share = hit.shares[s] ?? 0;
              const inactive = comp === undefined;
              return (
                <tr
                  key={s}
                  className={`border-t border-white/5 ${inactive ? 'opacity-40' : ''} ${
                    s === hit.dominant ? 'font-medium text-ink' : 'text-faint'
                  }`}
                >
                  <td className="py-1 pr-2">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className="inline-block h-2 w-2 rounded-sm"
                        style={{ backgroundColor: SIGNAL_COLOR[s] }}
                      />
                      {meta?.label ?? s}
                    </span>
                  </td>
                  <td className="py-1 pr-2 text-right">{inactive ? '—' : fmt(comp)}</td>
                  <td className="py-1 pr-2 text-right">{fmt(meta?.weight, 2)}</td>
                  <td className="py-1 pr-2 text-right">{fmt(contrib, 4)}</td>
                  <td className="py-1 text-right">{pct(share)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function RankingExplainView() {
  const [query, setQuery] = useState('quartz flotation recovery');
  const [topK, setTopK] = useState(10);

  const cat = useQuery({
    queryKey: ['ranking-signals'],
    queryFn: () => apiGet<SignalsResponse>('/api/v1/ranking/signals'),
  });

  const run = useMutation({
    mutationFn: () =>
      apiPost<ExplainResponse>('/api/v1/ranking/explain', { query, top_k: topK }),
  });

  const result = run.data;
  const signals = result?.signals ?? cat.data?.signals ?? [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">retrieval · explainability · §12.4</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Объяснимость ранжирования
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Пять сигналов fusion (§10.2) — <b>dense</b>, <b>sparse</b>, <b>BM25</b>,{' '}
          <b>близость в графе</b> и <b>качество доказательств</b> — считаются в живом
          retrieval-пути, но обычно скрыты за одной непрозрачной оценкой. Панель «почему тут»
          пересчитывает те же реальные сигналы над графом и раскладывает fused-оценку каждого
          хита на вклады <code className="text-ink">component × weight</code>, доли и
          доминирующий сигнал.
        </p>

        {/* Controls */}
        <div className="panel mb-5 p-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-[260px] flex-1">
              <label className="mb-1 block text-xs text-faint">Запрос</label>
              <div className="flex items-center gap-2 rounded border border-white/10 bg-black/20 px-2">
                <Search size={15} className="text-faint" />
                <input
                  className="w-full bg-transparent py-2 text-sm outline-none"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && query.trim() && run.mutate()}
                  placeholder="material X + regime Y + property Z…"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs text-faint">top_k</label>
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(e) => setTopK(Math.max(1, Math.min(50, Number(e.target.value) || 10)))}
                className="w-20 rounded border border-white/10 bg-black/20 px-2 py-1.5 text-sm outline-none"
              />
            </div>
            <button
              onClick={() => run.mutate()}
              disabled={run.isPending || !query.trim()}
              className="btn-copper flex items-center gap-2"
            >
              {run.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Sparkles size={16} />
              )}
              {run.isPending ? 'Считаю…' : 'Объяснить ранжирование'}
            </button>
          </div>
          {signals.length > 0 && (
            <div className="mt-3">
              <Legend signals={signals} />
            </div>
          )}
        </div>

        {run.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка: {(run.error as Error).message}
          </div>
        )}

        {result && (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-faint">
              <span className="rounded bg-black/20 px-2 py-1">
                хитов: <span className="text-ink">{result.count}</span>
              </span>
              <span className="rounded bg-black/20 px-2 py-1">
                активные сигналы:{' '}
                <span className="text-ink">{result.active_signals.join(', ') || '—'}</span>
              </span>
              {!result.dense_available && (
                <span
                  className="rounded bg-amber-500/15 px-2 py-1 text-amber-300"
                  title="entity vector index недоступен — dense-сигнал исключён и веса перенормированы"
                >
                  dense-индекс недоступен → веса перенормированы
                </span>
              )}
            </div>

            {result.count === 0 ? (
              <div className="panel p-4 text-sm text-faint">
                Ничего не найдено для «{result.query}». Попробуйте другие термины запроса.
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {result.hits.map((h, i) => (
                  <div key={h.id} className="flex gap-2">
                    <span className="mt-3 w-6 shrink-0 text-right text-sm font-semibold text-faint">
                      #{i + 1}
                    </span>
                    <div className="flex-1">
                      <HitCard hit={h} signals={signals} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {!result && !run.isPending && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Layers size={16} /> Введите запрос и нажмите «Объяснить ранжирование», чтобы увидеть
            раскладку fusion-сигналов по каждому хиту.
          </div>
        )}
      </div>
    </div>
  );
}
