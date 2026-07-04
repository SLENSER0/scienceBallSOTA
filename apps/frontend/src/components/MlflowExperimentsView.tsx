import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Beaker,
  CircleCheck,
  CircleSlash,
  FlaskConical,
  GitCommitHorizontal,
  Loader2,
  Play,
  Radio,
  Route,
  Server,
} from 'lucide-react';

// §18.4 Live MLflow tracking UI — experiments / runs / params / metrics (§15.2).
// Self-contained (no api.ts edits): calls the mlflow router directly with the same
// session-auth convention as api.ts / BenchmarkView.

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

async function apiPost<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

interface Status {
  mode: 'server' | 'offline';
  tracking_uri: string;
  mlflow_installed: boolean;
  configured: boolean;
  ui_url: string;
  experiments: string[];
  run_counts: Record<string, number>;
  total_runs: number;
  git_sha: string;
}

interface ExperimentSpec {
  name: string;
  tracked_params: string[];
  tracked_metrics: string[];
  run_count: number;
  latest_metrics: Record<string, number>;
}
interface ExperimentsResponse {
  experiments: ExperimentSpec[];
  mode: string;
  metrics_ref: string;
}

interface Run {
  run_id: string;
  experiment: string;
  params: Record<string, unknown>;
  metrics: Record<string, number>;
  tags: Record<string, string>;
  git_sha: string;
  dataset_version: string;
  start_time: number;
  source: string;
}
interface RunsResponse {
  runs: Run[];
  mode: string;
  count: number;
}

function fmt(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

const EXP_META: Record<string, { label: string; icon: typeof Beaker; hint: string }> = {
  extraction: { label: 'Extraction', icon: FlaskConical, hint: 'Извлечение сущностей/связей из текста' },
  retrieval: { label: 'Retrieval', icon: Beaker, hint: 'Поиск релевантных чанков/экспериментов' },
  answer: { label: 'Answer', icon: Route, hint: 'Синтез ответа поверх контекста' },
};

export function MlflowExperimentsView() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);

  const status = useQuery({
    queryKey: ['mlflow-status'],
    queryFn: () => apiGet<Status>('/api/v1/mlflow/status'),
  });
  const experiments = useQuery({
    queryKey: ['mlflow-experiments'],
    queryFn: () => apiGet<ExperimentsResponse>('/api/v1/mlflow/experiments'),
  });
  const runs = useQuery({
    queryKey: ['mlflow-runs', selected],
    queryFn: () =>
      apiGet<RunsResponse>(
        `/api/v1/mlflow/runs${selected ? `?experiment=${encodeURIComponent(selected)}` : ''}`,
      ),
  });

  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ['mlflow-status'] });
    qc.invalidateQueries({ queryKey: ['mlflow-experiments'] });
    qc.invalidateQueries({ queryKey: ['mlflow-runs'] });
  };

  const trackRetrieval = useMutation({
    mutationFn: () => apiPost<Run>('/api/v1/mlflow/track/retrieval'),
    onSuccess: refetchAll,
  });
  const trackExtraction = useMutation({
    mutationFn: () => apiPost<Run>('/api/v1/mlflow/track/extraction'),
    onSuccess: refetchAll,
  });

  const st = status.data;
  const isServer = st?.mode === 'server';

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">MLflow tracking · §18.4</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Эксперименты и прогоны</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Живой MLflow-трекинг трёх поверхностей — extraction / retrieval / answer — с params,
          метриками §15.2 и провенансом (<span className="font-mono">git_sha</span> +{' '}
          <span className="font-mono">dataset_version</span> + <span className="font-mono">trace_id</span>).
          Прогон записывается в реальный MLflow-сервер, когда он поднят, иначе — в офлайн-журнал
          (тот же результат виден в UI). Кнопки ниже запускают ЖИВОЙ прогон над текущим графом.
        </p>

        {/* Tracking backend status */}
        {st && (
          <div
            className={`panel mb-5 flex flex-wrap items-center gap-4 p-4 ${
              isServer ? 'border-emerald-500/40' : 'border-amber-500/40'
            }`}
          >
            {isServer ? (
              <Server size={26} className="text-emerald-400" />
            ) : (
              <Radio size={26} className="text-amber-400" />
            )}
            <div className="flex-1">
              <div className="font-display text-sm text-ink">
                {isServer ? 'MLflow tracking server подключён' : 'Офлайн-режим (in-memory + журнал)'}
              </div>
              <div className="text-xs text-faint">
                {isServer ? (
                  <>
                    Backend: <span className="font-mono text-ink">{st.tracking_uri}</span>
                    {st.ui_url && (
                      <>
                        {' · '}
                        <a
                          href={st.ui_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-copper underline"
                        >
                          открыть MLflow UI
                        </a>
                      </>
                    )}
                  </>
                ) : (
                  <>
                    MLFLOW_TRACKING_URI не задан — прогоны идут в{' '}
                    <span className="font-mono">&lt;artifacts&gt;/mlflow_runs.jsonl</span>. Задайте
                    URI, чтобы писать в общий сервер.
                  </>
                )}
              </div>
            </div>
            <div className="flex items-center gap-4 text-right">
              <div>
                <div className="font-display text-lg text-ink">{st.total_runs}</div>
                <div className="text-[10px] uppercase text-faint">прогонов</div>
              </div>
              <div className="flex items-center gap-1 text-xs text-faint">
                <GitCommitHorizontal size={14} />
                <span className="font-mono">{st.git_sha || 'n/a'}</span>
              </div>
            </div>
          </div>
        )}

        {/* Live-run actions */}
        <div className="mb-6 flex flex-wrap gap-3">
          <button
            onClick={() => trackRetrieval.mutate()}
            disabled={trackRetrieval.isPending}
            className="btn-copper flex items-center gap-2"
          >
            {trackRetrieval.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            {trackRetrieval.isPending ? 'Retrieval-прогон…' : 'Прогнать retrieval-eval'}
          </button>
          <button
            onClick={() => trackExtraction.mutate()}
            disabled={trackExtraction.isPending}
            className="btn-ghost flex items-center gap-2"
          >
            {trackExtraction.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            {trackExtraction.isPending ? 'Extraction-прогон…' : 'Замерить extraction-качество'}
          </button>
        </div>

        {(trackRetrieval.isError || trackExtraction.isError) && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка прогона:{' '}
            {((trackRetrieval.error || trackExtraction.error) as Error)?.message}
          </div>
        )}

        {/* Experiment cards */}
        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          {experiments.data?.experiments.map((e) => {
            const meta = EXP_META[e.name] ?? { label: e.name, icon: Beaker, hint: '' };
            const Icon = meta.icon;
            const active = selected === e.name;
            return (
              <button
                key={e.name}
                onClick={() => setSelected(active ? null : e.name)}
                className={`panel p-3 text-left transition ${
                  active ? 'border-copper' : 'hover:border-line'
                }`}
              >
                <div className="flex items-center gap-2">
                  <Icon size={16} className="text-copper" />
                  <span className="font-display text-sm text-ink">{meta.label}</span>
                  <span className="ml-auto rounded bg-void/40 px-2 py-0.5 font-mono text-xs text-faint">
                    {e.run_count} run{e.run_count === 1 ? '' : 's'}
                  </span>
                </div>
                <div className="mt-1 text-xs text-faint">{meta.hint}</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {e.tracked_metrics.slice(0, 4).map((m) => (
                    <span
                      key={m}
                      className="rounded bg-void/30 px-1.5 py-0.5 font-mono text-[10px] text-faint"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </button>
            );
          })}
        </div>

        {/* Runs table */}
        <div className="mb-2 flex items-center gap-2">
          <h3 className="font-display text-lg">
            Прогоны{selected ? ` · ${EXP_META[selected]?.label ?? selected}` : ' · все'}
          </h3>
          {selected && (
            <button
              onClick={() => setSelected(null)}
              className="text-xs text-copper underline"
            >
              сбросить фильтр
            </button>
          )}
        </div>

        {runs.isLoading ? (
          <div className="panel p-6 text-center text-faint">
            <Loader2 className="mx-auto animate-spin" />
          </div>
        ) : (runs.data?.runs.length ?? 0) === 0 ? (
          <div className="panel p-6 text-center text-sm text-faint">
            Пока нет прогонов. Запустите retrieval- или extraction-прогон выше.
          </div>
        ) : (
          <div className="space-y-3">
            {runs.data?.runs.map((r) => (
              <div key={r.run_id} className="panel p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="rounded bg-copper/15 px-2 py-0.5 text-xs font-semibold text-copper">
                    {EXP_META[r.experiment]?.label ?? r.experiment}
                  </span>
                  <span className="font-mono text-xs text-faint">{r.run_id}</span>
                  <span
                    className={`ml-auto flex items-center gap-1 text-[10px] uppercase ${
                      r.source === 'server' ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {r.source === 'server' ? (
                      <CircleCheck size={12} />
                    ) : (
                      <CircleSlash size={12} />
                    )}
                    {r.source}
                  </span>
                </div>

                {/* Provenance tags */}
                <div className="mb-3 flex flex-wrap gap-2 text-[11px]">
                  <span className="rounded bg-void/30 px-2 py-0.5 font-mono text-faint">
                    git_sha={r.git_sha || 'n/a'}
                  </span>
                  <span className="rounded bg-void/30 px-2 py-0.5 font-mono text-faint">
                    dataset={r.dataset_version || 'n/a'}
                  </span>
                  {r.tags?.trace_id && (
                    <span className="flex items-center gap-1 rounded bg-void/30 px-2 py-0.5 font-mono text-faint">
                      <Route size={11} /> {r.tags.trace_id}
                    </span>
                  )}
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  {/* Params */}
                  <div>
                    <div className="mb-1 text-[10px] uppercase text-faint">Параметры</div>
                    <div className="space-y-1">
                      {Object.entries(r.params).length === 0 && (
                        <div className="text-xs text-faint">—</div>
                      )}
                      {Object.entries(r.params).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2 text-xs">
                          <span className="text-faint">{k}</span>
                          <span className="font-mono text-ink">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* Metrics */}
                  <div>
                    <div className="mb-1 text-[10px] uppercase text-faint">Метрики §15.2</div>
                    <div className="space-y-1">
                      {Object.entries(r.metrics).length === 0 && (
                        <div className="text-xs text-faint">—</div>
                      )}
                      {Object.entries(r.metrics).map(([k, v]) => (
                        <div key={k} className="flex items-center justify-between gap-2 text-xs">
                          <span className="text-faint">{k}</span>
                          <span className="font-mono font-semibold text-emerald-400">
                            {fmt(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
