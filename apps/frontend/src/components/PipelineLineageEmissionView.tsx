import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertOctagon,
  ArrowRight,
  CheckCircle2,
  Database,
  FileJson,
  GitBranch,
  Loader2,
  PlayCircle,
  Radio,
  XCircle,
} from 'lucide-react';

// §10.5 pipeline-lineage *emission* UI. Companion to PipelineLineageView (which reads
// topology): this screen shows the OpenLineage RunEvents emitted for a real run — one
// event per §9.1 step with inputs→outputs, eventType (COMPLETE/FAIL/ABORT/START) and
// run-level facets (job_id, status, duration, counters). Self-contained (no api.ts edits):
// it calls the emission router directly with the same session-auth convention as api.ts.

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

interface CatalogJob {
  name: string;
  inputs: string[];
  outputs: string[];
}
interface CatalogDataset {
  name: string;
  serving: boolean;
}
interface Catalog {
  namespace: string;
  producer: string;
  jobs: CatalogJob[];
  datasets: CatalogDataset[];
  lineage_edges: { source: string; target: string }[];
}
interface RunRow {
  job_id: string;
  status: string;
  duration_s: number;
  n_documents: number;
  n_chunks: number;
  n_triples: number;
  extractor: string;
  created_at?: string;
  run_type?: string;
  source?: string;
}
interface RunsResponse {
  runs: RunRow[];
  count: number;
}
interface DatasetRef {
  namespace: string;
  name: string;
  facets?: Record<string, unknown>;
}
interface RunEvent {
  eventType: string;
  eventTime: string;
  producer: string;
  schemaURL: string;
  run: { runId: string; facets: Record<string, unknown> };
  job: { namespace: string; name: string; facets: Record<string, unknown> };
  inputs: DatasetRef[];
  outputs: DatasetRef[];
}
interface Emission {
  job_id: string;
  status: string;
  namespace: string;
  n_events: number;
  event_types: Record<string, number>;
  terminal_outputs: string[];
  lineage_edges: { source: string; target: string }[];
  events: RunEvent[];
  by_label?: Record<string, number>;
  run_type?: string;
  created_at?: string;
}

const STEP_LABEL: Record<string, string> = {
  register_source: 'Регистрация источника',
  docling_parse: 'Docling-парсинг',
  store_parsed_s3: 'Сохранение в S3',
  chunk: 'Чанкинг',
  extract: 'Извлечение триплетов',
  normalize_units: 'Нормализация единиц',
  entity_resolution: 'Разрешение сущностей',
  validate_schema: 'Валидация схемы',
  neo4j_upsert: 'Neo4j upsert',
  qdrant_index: 'Qdrant индекс',
  opensearch_index: 'OpenSearch индекс',
  gap_scan: 'Скан пробелов',
};

function eventTone(t: string): { cls: string; Icon: typeof CheckCircle2 } {
  switch (t) {
    case 'COMPLETE':
      return { cls: 'text-emerald-400 bg-emerald-500/15', Icon: CheckCircle2 };
    case 'FAIL':
      return { cls: 'text-red-400 bg-red-500/15', Icon: XCircle };
    case 'ABORT':
      return { cls: 'text-zinc-400 bg-zinc-500/15', Icon: AlertOctagon };
    default:
      return { cls: 'text-amber-400 bg-amber-500/15', Icon: Radio };
  }
}

function EventTypePill({ t, n }: { t: string; n: number }) {
  const { cls, Icon } = eventTone(t);
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${cls}`}>
      <Icon size={12} /> {t} · {n}
    </span>
  );
}

function runFacetNum(ev: RunEvent, key: string): number | undefined {
  const f = ev.run.facets?.pipelineRun as Record<string, unknown> | undefined;
  const v = f?.[key];
  return typeof v === 'number' ? v : undefined;
}

export function PipelineLineageEmissionView() {
  const [selected, setSelected] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState<'SUCCESS' | 'FAILED' | null>(null);

  const catalog = useQuery({
    queryKey: ['ple-catalog'],
    queryFn: () => apiGet<Catalog>('/api/v1/pipeline-lineage-emission/catalog'),
  });
  const runs = useQuery({
    queryKey: ['ple-runs'],
    queryFn: () => apiGet<RunsResponse>('/api/v1/pipeline-lineage-emission/runs?limit=100'),
  });

  const emissionUrl =
    previewMode !== null
      ? `/api/v1/pipeline-lineage-emission/preview?status=${previewMode}${
          previewMode === 'FAILED' ? '&failed_step=extract' : ''
        }`
      : selected
        ? `/api/v1/pipeline-lineage-emission/runs/${encodeURIComponent(selected)}/events`
        : null;

  const emission = useQuery({
    queryKey: ['ple-emission', emissionUrl],
    queryFn: () => apiGet<Emission>(emissionUrl!),
    enabled: !!emissionUrl,
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">lineage / emission · §10.5</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Эмиссия линиджа конвейера</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Реальная эмиссия pipeline-lineage в формате{' '}
          <span className="text-ink">OpenLineage</span>: каждый прогон §9.1 превращается в набор
          RunEvent — по одному на шаг, с рёбрами inputs→outputs и run-level фасетами (job_id,
          статус, длительность, счётчики). Успешный прогон даёт COMPLETE на всех шагах; упавший —
          FAIL на упавшем шаге и ABORT на его нисходящем конусе. Прогоны читаются из живого графа
          (ExtractorRun / GapScanRun) и SQL-реестра.
        </p>

        {/* Static §9.1 catalog */}
        <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
          <GitBranch size={18} className="text-copper" /> Каталог заданий §9.1 (OpenLineage jobs)
        </h3>
        {catalog.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка каталога…
          </div>
        )}
        {catalog.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка каталога: {(catalog.error as Error).message}
          </div>
        )}
        {catalog.data && (
          <div className="panel mb-6 p-4 text-xs text-faint">
            <div className="mb-2 flex flex-wrap gap-4">
              <span>
                namespace: <span className="font-mono text-ink">{catalog.data.namespace}</span>
              </span>
              <span>
                jobs: <span className="text-ink">{catalog.data.jobs.length}</span>
              </span>
              <span>
                datasets: <span className="text-ink">{catalog.data.datasets.length}</span>
              </span>
              <span>
                edges: <span className="text-ink">{catalog.data.lineage_edges.length}</span>
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {catalog.data.datasets.map((d) => (
                <span
                  key={d.name}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono ${
                    d.serving ? 'bg-copper/15 text-copper' : 'bg-white/[0.05] text-ink'
                  }`}
                >
                  {d.serving && <Database size={11} />}
                  {d.name}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Preview toggles */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-faint">Демо-эмиссия:</span>
          <button
            onClick={() => {
              setPreviewMode(previewMode === 'SUCCESS' ? null : 'SUCCESS');
              setSelected(null);
            }}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs ${
              previewMode === 'SUCCESS'
                ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                : 'border-white/10 text-faint hover:bg-white/[0.04]'
            }`}
          >
            <PlayCircle size={13} /> SUCCESS
          </button>
          <button
            onClick={() => {
              setPreviewMode(previewMode === 'FAILED' ? null : 'FAILED');
              setSelected(null);
            }}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs ${
              previewMode === 'FAILED'
                ? 'border-red-500/50 bg-red-500/10 text-red-400'
                : 'border-white/10 text-faint hover:bg-white/[0.04]'
            }`}
          >
            <XCircle size={13} /> FAILED @ extract
          </button>
        </div>

        {/* Real runs list */}
        <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
          <FileJson size={18} className="text-copper" /> Трассируемые прогоны
        </h3>
        {runs.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка прогонов…
          </div>
        )}
        {runs.data && runs.data.runs.length === 0 && (
          <div className="panel p-4 text-sm text-faint">
            Прогонов пока нет — используйте демо-эмиссию выше, чтобы увидеть форму событий.
          </div>
        )}
        {runs.data && runs.data.runs.length > 0 && (
          <div className="panel mb-2 overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-faint">
                  <th className="px-3 py-2">Job ID</th>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2 text-right">Док.</th>
                  <th className="px-3 py-2 text-right">Чанки</th>
                  <th className="px-3 py-2 text-right">Триплеты</th>
                  <th className="px-3 py-2">Источник</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.runs.map((r) => (
                  <tr
                    key={r.job_id}
                    onClick={() => {
                      setSelected(r.job_id === selected ? null : r.job_id);
                      setPreviewMode(null);
                    }}
                    className={`cursor-pointer border-b border-white/5 hover:bg-white/[0.04] ${
                      r.job_id === selected && previewMode === null ? 'bg-copper/[0.08]' : ''
                    }`}
                  >
                    <td className="max-w-[240px] truncate px-3 py-2 font-mono text-xs text-ink">
                      {r.job_id}
                    </td>
                    <td className="px-3 py-2 text-xs">{r.status}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.n_documents}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.n_chunks}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.n_triples}</td>
                    <td className="px-3 py-2 text-xs text-faint">{r.source || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Emitted events */}
        {emissionUrl && (
          <div className="mt-6">
            <h3 className="mb-2 font-display text-lg">
              Эмитированные события OpenLineage
              {previewMode && <span className="ml-2 text-sm text-faint">(демо: {previewMode})</span>}
            </h3>
            {emission.isLoading && (
              <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
                <Loader2 size={16} className="animate-spin" /> Эмиссия событий…
              </div>
            )}
            {emission.isError && (
              <div className="panel border-red-500/40 p-3 text-sm text-red-400">
                Ошибка эмиссии: {(emission.error as Error).message}
              </div>
            )}
            {emission.data && (
              <div className="space-y-3">
                <div className="panel flex flex-wrap items-center gap-3 p-3 text-xs text-faint">
                  <span>
                    job_id: <span className="font-mono text-ink">{emission.data.job_id}</span>
                  </span>
                  <span>
                    статус: <span className="text-ink">{emission.data.status}</span>
                  </span>
                  <span>
                    событий: <span className="text-ink">{emission.data.n_events}</span>
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(emission.data.event_types).map(([t, n]) => (
                      <EventTypePill key={t} t={t} n={n} />
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  {emission.data.events.map((ev) => {
                    const { cls, Icon } = eventTone(ev.eventType);
                    const docs = runFacetNum(ev, 'documents');
                    const chunks = runFacetNum(ev, 'chunks');
                    const triples = runFacetNum(ev, 'triples');
                    return (
                      <div key={ev.run.runId} className="panel p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <span
                              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${cls}`}
                            >
                              <Icon size={12} /> {ev.eventType}
                            </span>
                            <span className="font-display text-sm text-ink">
                              {STEP_LABEL[ev.job.name] ?? ev.job.name}
                            </span>
                            <span className="font-mono text-[10px] text-faint">{ev.job.name}</span>
                          </div>
                          <span className="font-mono text-[10px] text-faint">
                            {ev.run.runId.slice(0, 8)}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                          {ev.inputs.length === 0 ? (
                            <span className="text-faint/60">root</span>
                          ) : (
                            ev.inputs.map((i) => (
                              <span
                                key={i.name}
                                className="rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-faint"
                              >
                                {i.name}
                              </span>
                            ))
                          )}
                          <ArrowRight size={13} className="text-faint/60" />
                          {ev.outputs.length === 0 ? (
                            <span className="text-faint/60">sink</span>
                          ) : (
                            ev.outputs.map((o) => {
                              const serving = !!(o.facets && 'servingStore' in o.facets);
                              return (
                                <span
                                  key={o.name}
                                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono ${
                                    serving ? 'bg-copper/15 text-copper' : 'bg-white/[0.05] text-ink'
                                  }`}
                                >
                                  {serving && <Database size={10} />}
                                  {o.name}
                                </span>
                              );
                            })
                          )}
                        </div>
                        {(docs || chunks || triples) && (
                          <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-faint">
                            {docs ? <span>документов: {docs}</span> : null}
                            {chunks ? <span>чанков: {chunks}</span> : null}
                            {triples ? <span>триплетов: {triples}</span> : null}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
