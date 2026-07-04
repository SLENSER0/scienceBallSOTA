import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  FileText,
  Gauge,
  Layers,
  Loader2,
  Minus,
  Search,
  ShieldAlert,
} from 'lucide-react';

// §12.9 — Cross-encoder / rerank pass turned on in the LIVE retrieval path.
// Self-contained (no api.ts edits): calls the rerank router directly with the
// same session-auth convention as api.ts / BenchmarkView.

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

interface Factor {
  name: string;
  penalty: number;
  delta: number;
  reason: string;
}
interface FusionHit {
  id: string;
  rank: number;
  name: string;
  label: string | null;
  score: number;
  has_span: boolean;
  verified: boolean;
  confidence: number | null;
  evidence_count: number;
  components: Record<string, number>;
}
interface RerankedHit extends FusionHit {
  base_score: number;
  adjusted_score: number;
  span_penalty: number;
  confidence_penalty: number;
  fusion_rank: number | null;
  rank_delta: number;
  factors: Factor[];
}
interface RerankResponse {
  query: string;
  enabled: boolean;
  top_n: number;
  candidate_count: number;
  cross_encoder: { requested: boolean; model: string; used: boolean; available: boolean };
  fusion_order: FusionHit[];
  reranked_order: RerankedHit[];
  summary: {
    positions_changed: number;
    verified_or_span_promoted: number;
    passthrough: boolean;
    identical_to_fusion: boolean;
  };
  timings_ms: Record<string, number>;
}
interface ConfigResponse {
  config: { model: string; top_n: number; enabled: boolean; batch_size: number };
  penalties: {
    confidence_threshold: number;
    missing_span_penalty: number;
    low_confidence_penalty: number;
  };
  cross_encoder_importable: boolean;
}

function fmt(v: number | null): string {
  if (v === null || v === undefined) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

function DeltaBadge({ delta }: { delta: number }) {
  if (delta > 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-emerald-400" title="поднялся выше">
        <ArrowUpRight size={13} /> {delta}
      </span>
    );
  if (delta < 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-red-400" title="опустился ниже">
        <ArrowDownRight size={13} /> {Math.abs(delta)}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-0.5 text-faint" title="без изменений">
      <Minus size={13} />
    </span>
  );
}

function HitBadges({ hit }: { hit: FusionHit }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
      {hit.label && (
        <span className="rounded bg-black/20 px-1.5 py-0.5 text-faint">{hit.label}</span>
      )}
      {hit.verified && (
        <span className="inline-flex items-center gap-0.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-400">
          <BadgeCheck size={11} /> verified
        </span>
      )}
      <span
        className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 ${
          hit.has_span ? 'bg-sky-500/15 text-sky-400' : 'bg-amber-500/15 text-amber-400'
        }`}
        title={hit.has_span ? 'есть source span' : 'нет source span (штраф §12.9)'}
      >
        <FileText size={11} /> {hit.has_span ? 'span' : 'no span'}
      </span>
      {hit.confidence !== null && (
        <span
          className="inline-flex items-center gap-0.5 rounded bg-black/20 px-1.5 py-0.5 text-faint"
          title="confidence извлечения"
        >
          <Gauge size={11} /> {fmt(hit.confidence)}
        </span>
      )}
      {hit.evidence_count > 0 && (
        <span className="rounded bg-black/20 px-1.5 py-0.5 text-faint">
          ev×{hit.evidence_count}
        </span>
      )}
    </div>
  );
}

export function RerankLiveView() {
  const [query, setQuery] = useState('quartz flotation recovery');
  const [enabled, setEnabled] = useState(true);
  const [crossEncoder, setCrossEncoder] = useState(false);
  const [threshold, setThreshold] = useState(0.5);
  const [topN, setTopN] = useState(50);

  const cfg = useQuery({
    queryKey: ['rerank-config'],
    queryFn: () => apiGet<ConfigResponse>('/api/v1/rerank/config'),
  });

  const run = useMutation({
    mutationFn: () => {
      const p = new URLSearchParams({
        q: query,
        enabled: String(enabled),
        cross_encoder: String(crossEncoder),
        confidence_threshold: String(threshold),
        top_n: String(topN),
      });
      return apiGet<RerankResponse>(`/api/v1/rerank/live?${p.toString()}`);
    },
  });

  const result = run.data;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">retrieval · rerank · §12.9</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Cross-encoder reranker (live)</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Финальный rerank-проход §12.9 включён в живой retrieval-путь. Строим fusion-кандидатов
          над графом (keyword + evidence_quality, verified-буст внутри приора), затем применяем
          штрафы за <b>missing source span</b> и <b>low confidence</b> (опционально — cross-encoder
          скор как база). Слева fusion-порядок, справа reranked — со стрелками сдвига и раскладкой
          штрафов. Выключение реранка детерминированно возвращает fusion-порядок.
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
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              rerank on
            </label>
            <label
              className="flex cursor-pointer items-center gap-2 text-sm"
              title={
                cfg.data && !cfg.data.cross_encoder_importable
                  ? 'sentence-transformers недоступен — деградация к fusion-порядку'
                  : 'cross-encoder скор как база rerank'
              }
            >
              <input
                type="checkbox"
                checked={crossEncoder}
                onChange={(e) => setCrossEncoder(e.target.checked)}
              />
              cross-encoder
            </label>
            <div>
              <label className="mb-1 block text-xs text-faint">
                confidence threshold: {threshold.toFixed(2)}
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-faint">top_n</label>
              <input
                type="number"
                min={1}
                max={200}
                value={topN}
                onChange={(e) => setTopN(Math.max(1, Math.min(200, Number(e.target.value) || 50)))}
                className="w-20 rounded border border-white/10 bg-black/20 px-2 py-1.5 text-sm outline-none"
              />
            </div>
            <button
              onClick={() => run.mutate()}
              disabled={run.isPending || !query.trim()}
              className="btn-copper flex items-center gap-2"
            >
              {run.isPending ? <Loader2 size={16} className="animate-spin" /> : <Layers size={16} />}
              {run.isPending ? 'Rerank…' : 'Rerank'}
            </button>
          </div>
          {cfg.data && (
            <div className="mt-3 text-xs text-faint">
              model <code className="text-ink">{cfg.data.config.model}</code> · span-penalty{' '}
              {cfg.data.penalties.missing_span_penalty} · low-conf-penalty{' '}
              {cfg.data.penalties.low_confidence_penalty}
              {!cfg.data.cross_encoder_importable && (
                <span className="ml-2 text-amber-400">
                  · cross-encoder недоступен офлайн → fusion-порядок
                </span>
              )}
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
            {/* Summary */}
            <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="panel p-3">
                <div className="text-2xl font-semibold text-ink">{result.candidate_count}</div>
                <div className="text-xs text-faint">кандидатов после fusion</div>
              </div>
              <div className="panel p-3">
                <div className="text-2xl font-semibold text-ink">
                  {result.summary.positions_changed}
                </div>
                <div className="text-xs text-faint">позиций изменено реранком</div>
              </div>
              <div className="panel p-3">
                <div className="text-2xl font-semibold text-emerald-400">
                  {result.summary.verified_or_span_promoted}
                </div>
                <div className="text-xs text-faint">verified/span подняты выше</div>
              </div>
              <div className="panel p-3">
                <div className="text-2xl font-semibold text-ink">
                  {fmt(result.timings_ms.rerank)}ms
                </div>
                <div className="text-xs text-faint">
                  латентность rerank (retrieval {fmt(result.timings_ms.retrieval)}ms)
                </div>
              </div>
            </div>

            {result.summary.passthrough && (
              <div className="panel mb-4 flex items-center gap-2 border-amber-500/40 p-3 text-sm text-amber-300">
                <ShieldAlert size={16} /> rerank выключен — детерминированный passthrough:
                порядок == fusion-порядок.
              </div>
            )}
            {result.cross_encoder.requested && (
              <div
                className={`panel mb-4 p-3 text-sm ${
                  result.cross_encoder.used ? 'border-sky-500/40 text-sky-300' : 'border-amber-500/40 text-amber-300'
                }`}
              >
                cross-encoder{' '}
                {result.cross_encoder.used
                  ? `активен (${result.cross_encoder.model}) — скор как база rerank`
                  : `недоступен (${result.cross_encoder.model}) — деградация к fusion-приору`}
              </div>
            )}

            {/* Two-column before / after */}
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-2 font-display text-lg">Fusion-порядок</h3>
                <div className="space-y-2">
                  {result.fusion_order.slice(0, 20).map((h) => (
                    <div key={h.id} className="panel p-2.5">
                      <div className="flex items-baseline gap-2">
                        <span className="w-6 text-sm font-semibold text-faint">#{h.rank + 1}</span>
                        <span className="flex-1 text-sm text-ink">{h.name}</span>
                        <span className="text-xs text-faint">{fmt(h.score)}</span>
                      </div>
                      <div className="pl-8">
                        <HitBadges hit={h} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                  Reranked <ArrowRight size={16} className="text-copper" />
                </h3>
                <div className="space-y-2">
                  {result.reranked_order.slice(0, 20).map((h) => (
                    <div
                      key={h.id}
                      className={`panel p-2.5 ${h.rank_delta > 0 ? 'border-emerald-500/30' : ''}`}
                    >
                      <div className="flex items-baseline gap-2">
                        <span className="w-6 text-sm font-semibold text-faint">#{h.rank + 1}</span>
                        <span className="flex-1 text-sm text-ink">{h.name}</span>
                        <DeltaBadge delta={h.rank_delta} />
                        <span
                          className="text-xs text-faint"
                          title={`base ${fmt(h.base_score)} → adjusted ${fmt(h.adjusted_score)}`}
                        >
                          {fmt(h.adjusted_score)}
                        </span>
                      </div>
                      <div className="pl-8">
                        <HitBadges hit={h} />
                        {h.factors.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
                            {h.factors.map((f) => (
                              <span
                                key={f.name}
                                className="rounded bg-red-500/15 px-1.5 py-0.5 text-red-300"
                                title={f.reason}
                              >
                                −{fmt(f.penalty)} {f.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
