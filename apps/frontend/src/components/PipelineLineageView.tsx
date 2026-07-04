import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Database,
  GitBranch,
  Layers,
  Loader2,
  XCircle,
} from 'lucide-react';

// §10.5 pipeline-lineage UI. Self-contained (no api.ts edits): it calls the
// pipeline-lineage router directly with the same session-auth convention as api.ts.

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

interface StepSpec {
  name: string;
  inputs: string[];
  outputs: string[];
}
interface Topology {
  order: string[];
  cycles: string[][];
  sources: string[];
  sinks: string[];
  orphans: string[];
}
interface LineageGraph {
  steps: StepSpec[];
  edges: { source: string; target: string }[];
  terminal_outputs: string[];
  topology: Topology;
}
interface RunFacts {
  job_id: string;
  status: string;
  duration_s: number;
  n_documents: number;
  n_chunks: number;
  n_triples: number;
  extractor: string;
  model: string;
  created_at?: string;
  run_type?: string;
  source?: string;
  failed_step?: string;
  error?: string;
}
interface Rollup {
  n_runs: number;
  total_documents: number;
  total_chunks: number;
  total_triples: number;
  success_rate: number;
}
interface RunsResponse {
  runs: RunFacts[];
  rollup: Rollup;
}
interface FailureImpact {
  failed_step: string;
  blocked_steps: string[];
  impacted_stores: string[];
  is_terminal_impact: boolean;
}
interface RunDetail {
  run: RunFacts & { by_label?: Record<string, number> };
  lineage: LineageGraph;
  failure_impact?: FailureImpact;
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

const STORE_STEPS = new Set(['neo4j_upsert', 'qdrant_index', 'opensearch_index']);

function fmtDuration(s: number): string {
  if (!s) return '—';
  if (s < 60) return `${s.toFixed(1)} с`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m} м ${rem} с`;
}

function fmtNum(n: number): string {
  return n.toLocaleString('ru-RU');
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'SUCCESS')
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400">
        <CheckCircle2 size={12} /> SUCCESS
      </span>
    );
  if (status === 'FAILED')
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-xs text-red-400">
        <XCircle size={12} /> FAILED
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-400">
      <CircleDashed size={12} /> RUNNING
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

export function PipelineLineageView() {
  const [selected, setSelected] = useState<string | null>(null);

  const graph = useQuery({
    queryKey: ['pipeline-lineage-graph'],
    queryFn: () => apiGet<LineageGraph>('/api/v1/pipeline-lineage/graph'),
  });
  const runs = useQuery({
    queryKey: ['pipeline-lineage-runs'],
    queryFn: () => apiGet<RunsResponse>('/api/v1/pipeline-lineage/runs?limit=100'),
  });
  const detail = useQuery({
    queryKey: ['pipeline-lineage-run', selected],
    queryFn: () => apiGet<RunDetail>(`/api/v1/pipeline-lineage/runs/${encodeURIComponent(selected!)}`),
    enabled: !!selected,
  });

  const order = graph.data?.topology.order ?? [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">lineage / orchestration · §10.5</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Линидж конвейера</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          End-to-end трассируемость ingestion-конвейера (§9.1): реальный граф зависимостей от
          raw-источника до трёх обслуживающих хранилищ (Neo4j KG · Qdrant · OpenSearch), плюс
          run-level метаданные каждого прогона — job_id, статус, длительность и счётчики
          (документы / чанки / триплеты). Прогоны читаются из живого графа (ExtractorRun /
          GapScanRun) и, при наличии, из SQL-реестра запусков.
        </p>

        {/* Rollup summary */}
        {runs.data && (
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="Прогонов" value={fmtNum(runs.data.rollup.n_runs)} />
            <StatTile
              label="Успешность"
              value={`${Math.round(runs.data.rollup.success_rate * 100)}%`}
              hint="доля SUCCESS"
            />
            <StatTile label="Документов" value={fmtNum(runs.data.rollup.total_documents)} />
            <StatTile label="Чанков" value={fmtNum(runs.data.rollup.total_chunks)} />
            <StatTile label="Триплетов" value={fmtNum(runs.data.rollup.total_triples)} />
          </div>
        )}

        {/* Canonical §9.1 lineage DAG */}
        <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
          <GitBranch size={18} className="text-copper" /> Каноничный граф §9.1 (inputs→outputs)
        </h3>
        {graph.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка графа линиджа…
          </div>
        )}
        {graph.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка графа: {(graph.error as Error).message}
          </div>
        )}
        {graph.data && (
          <div className="panel mb-6 overflow-x-auto p-4">
            <div className="flex min-w-max items-center gap-1">
              {order.map((step, i) => {
                const isStore = STORE_STEPS.has(step);
                return (
                  <div key={step} className="flex items-center gap-1">
                    <div
                      className={`flex flex-col items-center rounded-lg border px-3 py-2 text-center ${
                        isStore
                          ? 'border-copper/50 bg-copper/10'
                          : 'border-white/10 bg-white/[0.03]'
                      }`}
                    >
                      {isStore ? (
                        <Database size={14} className="mb-1 text-copper" />
                      ) : (
                        <Layers size={14} className="mb-1 text-faint" />
                      )}
                      <div className="whitespace-nowrap text-xs text-ink">
                        {STEP_LABEL[step] ?? step}
                      </div>
                      <div className="mt-0.5 font-mono text-[10px] text-faint">{step}</div>
                    </div>
                    {i < order.length - 1 && (
                      <ArrowRight size={14} className="shrink-0 text-faint/60" />
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-faint">
              <span>
                Шагов: <span className="text-ink">{graph.data.steps.length}</span>
              </span>
              <span>
                Рёбер: <span className="text-ink">{graph.data.edges.length}</span>
              </span>
              <span>
                Обслуживающие хранилища:{' '}
                <span className="text-copper">{graph.data.terminal_outputs.join(' · ')}</span>
              </span>
              {graph.data.topology.cycles.length > 0 && (
                <span className="text-red-400">
                  ⚠ Циклы: {graph.data.topology.cycles.length}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Runs table */}
        <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
          <Activity size={18} className="text-copper" /> Трассируемые прогоны
        </h3>
        {runs.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка прогонов…
          </div>
        )}
        {runs.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка прогонов: {(runs.error as Error).message}
          </div>
        )}
        {runs.data && runs.data.runs.length === 0 && (
          <div className="panel p-4 text-sm text-faint">
            Прогонов пока нет — конвейер ещё не запускался на этом графе.
          </div>
        )}
        {runs.data && runs.data.runs.length > 0 && (
          <div className="panel overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-faint">
                  <th className="px-3 py-2">Job ID</th>
                  <th className="px-3 py-2">Тип</th>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2 text-right">Длит.</th>
                  <th className="px-3 py-2 text-right">Док.</th>
                  <th className="px-3 py-2 text-right">Чанки</th>
                  <th className="px-3 py-2 text-right">Триплеты</th>
                  <th className="px-3 py-2">Экстрактор</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.runs.map((r) => (
                  <tr
                    key={r.job_id}
                    onClick={() => setSelected(r.job_id === selected ? null : r.job_id)}
                    className={`cursor-pointer border-b border-white/5 hover:bg-white/[0.04] ${
                      r.job_id === selected ? 'bg-copper/[0.08]' : ''
                    }`}
                  >
                    <td className="max-w-[220px] truncate px-3 py-2 font-mono text-xs text-ink">
                      {r.job_id}
                    </td>
                    <td className="px-3 py-2 text-xs text-faint">{r.run_type || '—'}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-faint">
                      {fmtDuration(r.duration_s)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.n_documents)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.n_chunks)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.n_triples)}</td>
                    <td className="max-w-[160px] truncate px-3 py-2 text-xs text-faint">
                      {r.extractor || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Selected run detail */}
        {selected && (
          <div className="mt-6">
            <h3 className="mb-2 font-display text-lg">Прогон {selected}</h3>
            {detail.isLoading && (
              <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
                <Loader2 size={16} className="animate-spin" /> Загрузка деталей…
              </div>
            )}
            {detail.data && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <StatTile label="Статус" value={detail.data.run.status} />
                  <StatTile label="Длительность" value={fmtDuration(detail.data.run.duration_s)} />
                  <StatTile label="Тип" value={detail.data.run.run_type || '—'} />
                  <StatTile label="Источник" value={detail.data.run.source || '—'} />
                </div>

                {detail.data.run.by_label && Object.keys(detail.data.run.by_label).length > 0 && (
                  <div className="panel p-4">
                    <div className="mb-2 text-xs uppercase tracking-wide text-faint">
                      Произведено узлов по типам
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(detail.data.run.by_label)
                        .sort((a, b) => b[1] - a[1])
                        .map(([lbl, cnt]) => (
                          <span
                            key={lbl}
                            className="rounded-full bg-white/[0.05] px-2.5 py-1 text-xs text-ink"
                          >
                            {lbl}: <span className="text-copper">{fmtNum(cnt)}</span>
                          </span>
                        ))}
                    </div>
                  </div>
                )}

                {detail.data.failure_impact && (
                  <div className="panel border-red-500/40 p-4">
                    <div className="mb-2 flex items-center gap-2 text-sm text-red-400">
                      <AlertTriangle size={16} /> Радиус поражения (упал шаг{' '}
                      <span className="font-mono">{detail.data.failure_impact.failed_step}</span>)
                    </div>
                    <div className="text-xs text-faint">
                      Заблокированные шаги:{' '}
                      <span className="text-ink">
                        {detail.data.failure_impact.blocked_steps.join(', ') || '—'}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-faint">
                      Не обновлены хранилища:{' '}
                      <span className="text-red-400">
                        {detail.data.failure_impact.impacted_stores.join(', ') || 'нет'}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
