import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Boxes,
  CheckCircle2,
  CircleDashed,
  Database,
  GitBranch,
  Layers,
  Loader2,
  PlayCircle,
  Server,
  ServerCrash,
  Workflow,
} from 'lucide-react';

// §9.2 — Полный asset-граф Dagster + сквозная материализация seed-документа.
// Self-contained (no api.ts/types.ts edits): calls the dagster-assets router
// directly with the same session-auth convention as api.ts.

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

interface AssetNode {
  key: string;
  group_name: string;
  step: string;
  kind: string;
  title: string;
  description: string;
  deps: string[];
  evidence_labels: string[];
  serving: string | null;
  aggregate: string | null;
  corpus_count: number;
  status: string;
}
interface LayerBucket {
  group: string;
  assets: string[];
}
interface AssetJob {
  name: string;
  selection: string[];
  assets: string[];
  run_closure: string[];
}
interface Dagit {
  available: boolean;
  url: string;
  mode: string;
}
interface AssetGraph {
  assets: AssetNode[];
  edges: { source: string; target: string }[];
  topo_order: string[];
  layers: LayerBucket[];
  roots: string[];
  leaves: string[];
  jobs: AssetJob[];
  asset_count: number;
  layer_order: string[];
  dagit: Dagit;
  corpus_totals: { nodes: number; rels: number; communities: number };
}
interface Stage {
  order: number;
  key: string;
  group: string;
  step: string;
  title: string;
  description: string;
  kind: string;
  deps: string[];
  scope: string;
  status: string;
  count: number;
  serving: string | null;
}
interface MaterializeRun {
  seed: {
    doc_id: string;
    fragment: string;
    source: string;
    resolved: boolean;
    node_total: number;
    by_label: Record<string, number>;
  };
  job: string;
  dagit: Dagit;
  stages: Stage[];
  summary: {
    total: number;
    materialized: number;
    projected: number;
    empty: number;
    doc_nodes_total: number;
    corpus_nodes: number;
    corpus_rels: number;
  };
  criterion: string;
}

const LAYER_LABEL: Record<string, string> = {
  raw: 'RAW · источник',
  parse: 'PARSE · разбор',
  extract: 'EXTRACT · извлечение',
  graph: 'GRAPH · граф',
  index: 'INDEX · индексы',
  analytics: 'ANALYTICS · аналитика',
};

const JOB_LABEL: Record<string, string> = {
  full_ingestion_job: 'Полный конвейер',
  parse_only_job: 'Только разбор',
  extract_only_job: 'Только извлечение',
  reindex_job: 'Переиндексация',
  community_summary_job: 'Сообщества',
  gap_scan_job: 'Скан пробелов',
};

function fmtNum(n: number): string {
  return (n ?? 0).toLocaleString('ru-RU');
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'materialized')
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400">
        <CheckCircle2 size={12} /> materialized
      </span>
    );
  if (status === 'projected')
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-xs text-sky-400">
        <CircleDashed size={12} /> projected
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-500/15 px-2 py-0.5 text-xs text-faint">
      <CircleDashed size={12} /> empty
    </span>
  );
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="panel p-3">
      <div className="text-xs uppercase tracking-wide text-faint">{label}</div>
      <div className="mt-1 font-display text-xl text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-faint">{hint}</div>}
    </div>
  );
}

export function DagsterAssetGraphView() {
  const [job, setJob] = useState('full_ingestion_job');
  const [docId, setDocId] = useState('');

  const graph = useQuery({
    queryKey: ['dagster-assets-graph'],
    queryFn: () => apiGet<AssetGraph>('/api/v1/dagster-assets/graph'),
  });

  const materialize = useMutation({
    mutationFn: () =>
      apiPost<MaterializeRun>('/api/v1/dagster-assets/materialize', {
        job,
        doc_id: docId.trim() || null,
      }),
  });

  const assetByKey = useMemo(() => {
    const m = new Map<string, AssetNode>();
    (graph.data?.assets ?? []).forEach((a) => m.set(a.key, a));
    return m;
  }, [graph.data]);

  const dagit = graph.data?.dagit;
  const run = materialize.data;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">orchestration / dagster · §9.2</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Asset-граф Dagster</h2>
        <p className="mb-4 max-w-3xl text-sm text-faint">
          Полный software-defined asset-граф ingestion/indexing конвейера (§9.2): {' '}
          {graph.data?.asset_count ?? 12}+ ассетов от <code>source_registration</code> до{' '}
          <code>retrieval_eval</code> с зависимостями по слоям raw → parse → extract → graph →
          index → analytics. Проекция ассетов в UI/JSON, когда Dagit недоступен, плюс сквозная
          материализация seed-документа end-to-end по живому графу.
        </p>

        {/* Dagit availability banner */}
        {dagit && (
          <div
            className={`panel mb-5 flex items-center gap-3 p-3 text-sm ${
              dagit.available ? 'text-emerald-400' : 'text-amber-400'
            }`}
          >
            {dagit.available ? <Server size={16} /> : <ServerCrash size={16} />}
            {dagit.available ? (
              <span>
                Dagit доступен на <code>{dagit.url}</code> — граф также виден в нативном Dagit UI.
              </span>
            ) : (
              <span>
                Dagit ({dagit.url}) недоступен — режим <b>projection</b>: asset-граф и
                материализация спроецированы в UI/JSON из живого графа (§9.2).
              </span>
            )}
          </div>
        )}

        {/* Corpus totals */}
        {graph.data && (
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Ассетов" value={fmtNum(graph.data.asset_count)} hint="≥12 по §9.2" />
            <StatTile label="Узлов графа" value={fmtNum(graph.data.corpus_totals.nodes)} />
            <StatTile label="Связей" value={fmtNum(graph.data.corpus_totals.rels)} />
            <StatTile label="Сообществ" value={fmtNum(graph.data.corpus_totals.communities)} />
          </div>
        )}

        {graph.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка asset-графа…
          </div>
        )}
        {graph.isError && (
          <div className="panel p-4 text-sm text-red-400">
            Не удалось загрузить asset-граф: {String((graph.error as Error)?.message)}
          </div>
        )}

        {/* Asset graph by layer */}
        {graph.data && (
          <>
            <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
              <Layers size={18} className="text-copper" /> Слои конвейера
            </h3>
            <div className="mb-6 space-y-3">
              {graph.data.layers.map((layer) => (
                <div key={layer.group} className="panel p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-faint">
                    <Boxes size={14} /> {LAYER_LABEL[layer.group] ?? layer.group}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {layer.assets.map((key) => {
                      const a = assetByKey.get(key);
                      if (!a) return null;
                      return (
                        <div key={key} className="rounded-lg border border-white/5 bg-white/5 p-2.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-xs text-ink">{a.key}</span>
                            <StatusBadge status={a.status} />
                          </div>
                          <div className="mt-1 text-[11px] uppercase tracking-wide text-faint">
                            {a.step}
                          </div>
                          <div className="mt-1 text-xs text-faint">{a.title}</div>
                          <div className="mt-1.5 flex items-center justify-between text-[11px] text-faint">
                            <span className="inline-flex items-center gap-1">
                              <Database size={11} /> {fmtNum(a.corpus_count)}
                            </span>
                            {a.serving && (
                              <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-sky-400">
                                {a.serving}
                              </span>
                            )}
                          </div>
                          {a.deps.length > 0 && (
                            <div className="mt-1 truncate text-[10px] text-faint" title={a.deps.join(', ')}>
                              ← {a.deps.join(', ')}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Jobs */}
            <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
              <Workflow size={18} className="text-copper" /> Asset-джобы (define_asset_job)
            </h3>
            <div className="mb-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {graph.data.jobs.map((j) => (
                <button
                  key={j.name}
                  onClick={() => setJob(j.name)}
                  className={`panel p-3 text-left transition ${
                    job === j.name ? 'ring-1 ring-copper' : 'hover:bg-white/5'
                  }`}
                >
                  <div className="font-mono text-xs text-ink">{j.name}</div>
                  <div className="mt-0.5 text-xs text-faint">{JOB_LABEL[j.name] ?? ''}</div>
                  <div className="mt-1 text-[11px] text-faint">
                    {j.selection.length} ассет(ов) · closure {j.run_closure.length}
                  </div>
                </button>
              ))}
            </div>
          </>
        )}

        {/* End-to-end materialization */}
        <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
          <GitBranch size={18} className="text-copper" /> Сквозная материализация seed-документа
        </h3>
        <div className="panel mb-4 flex flex-wrap items-center gap-2 p-3">
          <input
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            placeholder="doc_id (пусто = авто-выбор seed-документа)"
            className="min-w-[16rem] flex-1 rounded-md border border-white/10 bg-black/20 px-3 py-1.5 text-sm text-ink outline-none focus:border-copper"
          />
          <span className="rounded-md border border-white/10 px-2 py-1.5 text-xs text-faint">
            job: <b className="text-ink">{job}</b>
          </span>
          <button
            onClick={() => materialize.mutate()}
            disabled={materialize.isPending}
            className="inline-flex items-center gap-1.5 rounded-md bg-copper/90 px-3 py-1.5 text-sm font-medium text-black hover:bg-copper disabled:opacity-50"
          >
            {materialize.isPending ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <PlayCircle size={15} />
            )}
            Материализовать
          </button>
        </div>

        {materialize.isError && (
          <div className="panel mb-4 p-3 text-sm text-red-400">
            Ошибка материализации: {String((materialize.error as Error)?.message)}
          </div>
        )}

        {run && (
          <div className="mb-8">
            <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile
                label="Seed-документ"
                value={run.seed.doc_id}
                hint={`${run.seed.source} · ${fmtNum(run.seed.node_total)} узлов`}
              />
              <StatTile label="Materialized" value={fmtNum(run.summary.materialized)} hint="из графа" />
              <StatTile label="Projected" value={fmtNum(run.summary.projected)} hint="внешние стораджи" />
              <StatTile label="Empty" value={fmtNum(run.summary.empty)} />
            </div>

            <div className="panel divide-y divide-white/5">
              {run.stages.map((s) => (
                <div key={s.key} className="flex items-start gap-3 p-3">
                  <div className="mt-0.5 w-6 shrink-0 text-right font-mono text-xs text-faint">
                    {s.order}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-ink">{s.key}</span>
                      <StatusBadge status={s.status} />
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-faint">
                        {s.group} · {s.scope}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[11px] uppercase tracking-wide text-faint">
                      {s.step}
                    </div>
                    <div className="mt-0.5 text-xs text-faint">{s.title}</div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="font-display text-lg text-ink">{fmtNum(s.count)}</div>
                    <div className="text-[10px] text-faint">
                      {s.serving ? s.serving : 'узлов'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-faint">{run.criterion}</p>
          </div>
        )}
      </div>
    </div>
  );
}
