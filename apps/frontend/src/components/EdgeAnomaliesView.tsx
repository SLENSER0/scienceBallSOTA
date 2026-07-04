import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  GitFork,
  Loader2,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { api } from '../api';

// §13.11 / §8.13 — Structural edge-anomaly inspector (Mode D graph hygiene).
// The detector already computes two structural smells that MERGE-dedup cannot
// catch; here a curator sees «подозрительное ребро» at a glance so broken
// extractions / mis-resolved coreferences never slip through. Read-only.

export interface EdgeSelfLoop {
  kind: 'self_loop';
  node_id: string;
  node_name: string | null;
  node_label: string | null;
  rel_type: string;
  label_ru: string;
  reason: string;
}

export interface EdgeParallel {
  kind: 'parallel_edge';
  src_id: string;
  src_name: string | null;
  src_label: string | null;
  dst_id: string;
  dst_name: string | null;
  dst_label: string | null;
  rel_types: string[];
  label_ru: string;
  reason: string;
}

export interface EdgeAnomalyReport {
  total_edges: number;
  n_self_loops: number;
  n_parallel_edges: number;
  n_anomalies: number;
  ok: boolean;
  health_score: number;
  counts: Record<string, number>;
  self_loops: EdgeSelfLoop[];
  parallel_edges: EdgeParallel[];
  truncated: boolean;
}

type Kind = 'self_loop' | 'parallel_edge';

const KIND_META: Record<Kind, { short: string; icon: typeof GitFork; ru: string }> = {
  self_loop: { short: 'петли', icon: RotateCcw, ru: 'ребро на самого себя' },
  parallel_edge: { short: 'параллельные', icon: GitFork, ru: 'конфликт семантики связи' },
};

function nodeToken(name: string | null, label: string | null, id: string): string {
  if (name && label) return `${name} · ${label}`;
  if (name) return name;
  return id;
}

function healthTone(score: number): string {
  if (score >= 0.999) return 'text-nickel-bright';
  if (score >= 0.98) return 'text-copper';
  return 'text-rust';
}

export function EdgeAnomaliesView() {
  const [kind, setKind] = useState<Kind | null>(null);

  const q = useQuery<EdgeAnomalyReport, Error>({
    queryKey: ['edge-anomalies'],
    queryFn: () => api.edgeAnomalies(),
  });

  const data = q.data;
  const counts = data?.counts ?? {};

  const showLoops = kind === null || kind === 'self_loop';
  const showParallel = kind === null || kind === 'parallel_edge';

  const loops = useMemo(() => (showLoops ? data?.self_loops ?? [] : []), [data, showLoops]);
  const parallel = useMemo(
    () => (showParallel ? data?.parallel_edges ?? [] : []),
    [data, showParallel],
  );
  const empty = loops.length === 0 && parallel.length === 0;

  const healthPct = data ? Math.round(data.health_score * 1000) / 10 : null;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">graph hygiene · Mode D · §13.11 / §8.13</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Аномалии рёбер — инспектор структурных дефектов графа
        </h2>
        <p className="mb-6 max-w-3xl text-sm text-muted">
          Два структурных сигнала, которые не ловит дедупликация при <code>MERGE</code>:{' '}
          <b>петли</b> (ребро узла на самого себя — почти всегда сломанная экстракция или ошибочная
          кореференция) и <b>параллельные рёбра</b> (одна и та же направленная связь под разными
          типами — конфликт семантики). Инспектор только читает граф — ничего не меняет.
        </p>

        {/* -- Health headline + filter chips ------------------------------ */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {data && (
            <div className="panel mr-1 flex items-center gap-2 px-3 py-1.5 text-sm">
              {data.ok ? (
                <ShieldCheck size={16} className="text-nickel-bright" />
              ) : (
                <ShieldAlert size={16} className="text-copper" />
              )}
              <span className="text-muted">доверие к рёбрам</span>
              <span className={`font-semibold tabular-nums ${healthTone(data.health_score)}`}>
                {healthPct}%
              </span>
            </div>
          )}
          <button
            onClick={() => setKind(null)}
            className={`rounded-full border px-3 py-1 text-xs ${
              kind === null
                ? 'border-copper/60 bg-copper/10 text-copper'
                : 'border-line text-muted hover:text-ink'
            }`}
          >
            все{data ? ` · ${data.n_anomalies}` : ''}
          </button>
          {(Object.keys(KIND_META) as Kind[]).map((k) => {
            const M = KIND_META[k];
            const Icon = M.icon;
            return (
              <button
                key={k}
                onClick={() => setKind(kind === k ? null : k)}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                  kind === k
                    ? 'border-copper/60 bg-copper/10 text-copper'
                    : 'border-line text-muted hover:text-ink'
                }`}
              >
                <Icon size={13} /> {M.short}
                <span className="text-faint">{counts[k] ?? 0}</span>
              </button>
            );
          })}
          <button
            onClick={() => q.refetch()}
            className="ml-auto flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:text-ink"
            disabled={q.isFetching}
          >
            {q.isFetching ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            обновить
          </button>
        </div>

        {q.isError && (
          <div className="panel mb-4 flex items-center gap-2 border-rust/40 p-3 text-sm text-rust">
            <TriangleAlert size={16} /> Не удалось загрузить отчёт: {q.error.message}
          </div>
        )}

        {data && (
          <div className="mb-4 text-xs text-faint">
            просканировано {data.total_edges} рёбер · петель {data.n_self_loops} · параллельных{' '}
            {data.n_parallel_edges}
            {data.truncated && ' · список усечён (показаны первые записи)'}
          </div>
        )}

        {/* -- Report ----------------------------------------------------- */}
        {q.isLoading ? (
          <div className="panel flex items-center gap-2 p-4 text-sm text-muted">
            <Loader2 size={16} className="animate-spin" /> Сканируем рёбра графа…
          </div>
        ) : empty ? (
          <div className="panel flex items-center gap-2 p-4 text-sm text-muted">
            <ShieldCheck size={16} className="text-nickel-bright" /> Структурных аномалий не найдено
            — граф чистый.
          </div>
        ) : (
          <div className="space-y-2.5">
            {loops.map((s, i) => (
              <div
                key={`loop-${s.node_id}-${s.rel_type}-${i}`}
                className="panel border-copper/40 p-3.5"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 rounded-full border border-copper/50 bg-copper/10 px-2 py-0.5 text-xs text-copper">
                    <RotateCcw size={12} /> {s.label_ru}
                  </span>
                  <code className="rounded bg-surface/60 px-1.5 py-0.5 text-xs text-muted">
                    {s.rel_type}
                  </code>
                  <span className="text-sm font-medium text-ink">
                    {nodeToken(s.node_name, s.node_label, s.node_id)}
                  </span>
                </div>
                <div className="text-sm text-muted">{s.reason}</div>
                <div className="mt-1 font-mono text-[11px] text-faint">id: {s.node_id}</div>
              </div>
            ))}
            {parallel.map((p, i) => (
              <div
                key={`par-${p.src_id}-${p.dst_id}-${i}`}
                className="panel border-nickel/40 p-3.5"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 rounded-full border border-nickel/40 bg-nickel/10 px-2 py-0.5 text-xs text-nickel-bright">
                    <GitFork size={12} /> {p.label_ru}
                  </span>
                  {p.rel_types.map((rt) => (
                    <code
                      key={rt}
                      className="rounded bg-surface/60 px-1.5 py-0.5 text-xs text-muted"
                    >
                      {rt}
                    </code>
                  ))}
                </div>
                <div className="text-sm text-ink">
                  {nodeToken(p.src_name, p.src_label, p.src_id)}{' '}
                  <span className="text-faint">→</span>{' '}
                  {nodeToken(p.dst_name, p.dst_label, p.dst_id)}
                </div>
                <div className="mt-0.5 text-sm text-muted">{p.reason}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
