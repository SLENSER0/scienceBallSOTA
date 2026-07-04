import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Beaker,
  CheckCircle2,
  Cpu,
  FileSearch,
  Fingerprint,
  GitBranch,
  Link2,
  Link2Off,
  Loader2,
  Search,
  Wrench,
} from 'lucide-react';

// §6.14 — ExtractorRun provenance & reproducibility.
// Каждое доказательство (Evidence) знает, каким прогоном и какой моделью извлечено.
// Backend: /api/v1/extractor-runs. Прогон материализуется узлом :ExtractorRun
// (модель/версии/seed/params), связь (:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)
// привязывает каждое доказательство к прогону. Панель показывает воспроизводимые
// метаданные, полноту lineage (сколько Evidence уже связано ребром EXTRACTED_BY),
// умеет достроить недостающие рёбра (curator) и разрешить lineage одного Evidence.
//
// Self-contained fetch (reads the session token like api.ts) so it needs no edits
// to shared hub files; swap to `api.extractorRun*` once those methods are wired.

interface RunSummary {
  run_id: string;
  name: string | null;
  extractor: string | null;
  model: string | null;
  pipeline_version: string | null;
  schema_version: string | null;
  created_at: string | null;
  evidence_by_prop: number;
  evidence_by_edge: number;
  lineage_complete: boolean;
  missing_edges: number;
}

interface RunListResponse {
  runs: RunSummary[];
  total_runs: number;
  total_missing_edges: number;
  fully_linked: boolean;
}

interface RunDetail {
  run_id: string;
  name: string | null;
  created_at: string | null;
  reproducibility: Record<string, unknown>;
  produced_by_label: Record<string, number>;
  evidence_by_prop: number;
  evidence_by_edge: number;
  lineage_complete: boolean;
  missing_edges: number;
  evidence_sample: string[];
}

interface EvidenceLineage {
  evidence_id: string;
  found: boolean;
  run_id: string | null;
  linked_via: string | null;
  extractor: string | null;
  model: string | null;
  pipeline_version: string | null;
  schema_version: string | null;
  run: Record<string, unknown> | null;
}

interface MaterializeResult {
  run_id: string;
  evidence_by_prop: number;
  edges_before: number;
  edges_created: number;
  edges_after: number;
  lineage_complete: boolean;
}

const BASE = '/api/v1/extractor-runs';

function session(): { token?: string; role?: string } {
  try {
    const raw = localStorage.getItem('sb.session');
    if (raw) return JSON.parse(raw) as { token?: string; role?: string };
  } catch {
    /* ignore */
  }
  return {};
}

function authHeaders(): Record<string, string> {
  const s = session();
  if (s.token) return { Authorization: `Bearer ${s.token}` };
  if (s.role) return { 'X-Role': s.role };
  return {};
}

function canWrite(): boolean {
  const role = session().role ?? '';
  return ['curator', 'admin', 'project_manager'].includes(role);
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: 'POST', headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function ExtractorRunLineageView() {
  const [selected, setSelected] = useState<string | null>(null);
  const [evQuery, setEvQuery] = useState('');
  const [evLookup, setEvLookup] = useState<string | null>(null);
  const qc = useQueryClient();

  const runs = useQuery({
    queryKey: ['extractor-runs'],
    queryFn: () => getJSON<RunListResponse>(BASE),
  });

  const detail = useQuery({
    queryKey: ['extractor-run', selected],
    queryFn: () => getJSON<RunDetail>(`${BASE}/${encodeURIComponent(selected!)}`),
    enabled: !!selected,
  });

  const lineage = useQuery({
    queryKey: ['extractor-run-evidence', evLookup],
    queryFn: () =>
      getJSON<EvidenceLineage>(`${BASE}/evidence/${encodeURIComponent(evLookup!)}`),
    enabled: !!evLookup,
  });

  const materialize = useMutation({
    mutationFn: (runId: string) =>
      postJSON<MaterializeResult>(`${BASE}/${encodeURIComponent(runId)}/materialize-edges`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['extractor-runs'] });
      qc.invalidateQueries({ queryKey: ['extractor-run', selected] });
    },
  });

  const data = runs.data;

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col overflow-y-auto p-6">
      <header className="mb-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Fingerprint size={16} className="text-copper" /> Прогоны экстрактора · lineage
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-faint">
          каждое доказательство знает, каким прогоном и моделью извлечено — версии, seed,
          params и связь EXTRACTED_BY (§6.14)
        </div>
      </header>

      {runs.isLoading ? (
        <div className="flex items-center gap-2 font-mono text-[12px] text-faint">
          <Loader2 size={14} className="animate-spin text-copper" /> загрузка прогонов…
        </div>
      ) : runs.isError ? (
        <div className="text-sm text-contradiction">Не удалось загрузить прогоны экстрактора.</div>
      ) : data ? (
        <>
          <LineageBanner data={data} />
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <RunList
              runs={data.runs}
              selected={selected}
              onSelect={(id) => setSelected(id === selected ? null : id)}
            />
            <div className="flex flex-col gap-4">
              {selected ? (
                detail.isLoading ? (
                  <div className="panel flex items-center gap-2 p-4 font-mono text-[12px] text-faint">
                    <Loader2 size={14} className="animate-spin text-copper" /> карточка прогона…
                  </div>
                ) : detail.data ? (
                  <RunCard
                    detail={detail.data}
                    onMaterialize={() => materialize.mutate(detail.data!.run_id)}
                    materializing={materialize.isPending}
                    result={
                      materialize.data?.run_id === detail.data.run_id
                        ? materialize.data
                        : undefined
                    }
                  />
                ) : (
                  <div className="panel p-4 text-sm text-contradiction">Прогон не найден.</div>
                )
              ) : (
                <div className="panel p-4 font-mono text-[12px] text-faint">
                  Выберите прогон слева, чтобы увидеть воспроизводимые метаданные и что он извлёк.
                </div>
              )}
              <EvidenceLookup
                query={evQuery}
                onQuery={setEvQuery}
                onSubmit={() => setEvLookup(evQuery.trim() || null)}
                loading={lineage.isFetching}
                result={evLookup ? lineage.data : undefined}
                error={lineage.isError}
              />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function LineageBanner({ data }: { data: RunListResponse }) {
  return (
    <div className="panel mb-4 flex flex-wrap items-center gap-4 p-4">
      <div>
        <div className="metric text-3xl text-copper">{data.total_runs}</div>
        <div className="font-mono text-[10px] text-faint">прогонов экстрактора</div>
      </div>
      <div className="h-8 w-px bg-line" />
      <div>
        <div
          className={`metric text-3xl ${
            data.fully_linked ? 'text-verified' : 'text-gap'
          }`}
        >
          {data.total_missing_edges}
        </div>
        <div className="font-mono text-[10px] text-faint">Evidence без ребра EXTRACTED_BY</div>
      </div>
      <div className="ml-auto">
        {data.fully_linked ? (
          <span className="chip text-verified border-verified/40">
            <CheckCircle2 size={11} /> lineage полон
          </span>
        ) : (
          <span className="chip text-gap border-gap/40">
            <Link2Off size={11} /> есть неполный lineage
          </span>
        )}
      </div>
    </div>
  );
}

function RunList({
  runs,
  selected,
  onSelect,
}: {
  runs: RunSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (!runs.length) {
    return (
      <div className="panel p-4 font-mono text-[12px] text-faint">
        В графе нет узлов :ExtractorRun.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {runs.map((r) => {
        const active = r.run_id === selected;
        return (
          <button
            key={r.run_id}
            onClick={() => onSelect(r.run_id)}
            className={`panel w-full p-3 text-left transition-colors ${
              active ? 'border-copper/60 bg-copper/5' : 'hover:border-line'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 font-mono text-[12px] text-nickel">
                <Beaker size={12} className="text-copper" />
                {r.name || r.extractor || r.run_id}
              </span>
              {r.lineage_complete ? (
                <span className="chip text-verified border-verified/40">
                  <Link2 size={10} /> связан
                </span>
              ) : (
                <span className="chip text-gap border-gap/40">
                  <Link2Off size={10} /> {r.missing_edges} без ребра
                </span>
              )}
            </div>
            <div className="mt-1 truncate font-mono text-[10px] text-faint">{r.run_id}</div>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-[10px] text-muted">
              {r.model && (
                <span className="inline-flex items-center gap-1">
                  <Cpu size={10} /> {r.model}
                </span>
              )}
              {r.pipeline_version && <span>pipeline {r.pipeline_version}</span>}
              {r.schema_version && <span>schema {r.schema_version}</span>}
              <span className="ml-auto text-faint">
                {r.evidence_by_edge}/{r.evidence_by_prop} Evidence
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function RunCard({
  detail,
  onMaterialize,
  materializing,
  result,
}: {
  detail: RunDetail;
  onMaterialize: () => void;
  materializing: boolean;
  result?: MaterializeResult;
}) {
  const repro = Object.entries(detail.reproducibility);
  const produced = Object.entries(detail.produced_by_label).sort((a, b) => b[1] - a[1]);
  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5 font-mono text-[13px] text-nickel">
            <GitBranch size={13} className="text-copper" /> {detail.name || detail.run_id}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-faint">{detail.run_id}</div>
        </div>
        {detail.lineage_complete ? (
          <span className="chip text-verified border-verified/40">
            <CheckCircle2 size={11} /> lineage полон
          </span>
        ) : (
          <span className="chip text-gap border-gap/40">
            <Link2Off size={11} /> {detail.missing_edges} без ребра
          </span>
        )}
      </div>

      {/* Reproducibility params */}
      <div className="mb-3">
        <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
          воспроизводимость (модель · версии · seed · params)
        </div>
        {repro.length ? (
          <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
            {repro.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2 border-b border-line/40 py-0.5">
                <span className="font-mono text-[10px] text-faint">{k}</span>
                <span className="truncate text-right font-mono text-[10px] text-muted" title={fmtVal(v)}>
                  {fmtVal(v)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="font-mono text-[10px] text-faint">нет метаданных на узле прогона</div>
        )}
      </div>

      {/* Produced-by-label */}
      <div className="mb-3">
        <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
          извлечено этим прогоном (по меткам, provenance-штамп extractor_run_id)
        </div>
        {produced.length ? (
          <div className="flex flex-wrap gap-1.5">
            {produced.map(([label, n]) => (
              <span key={label} className="chip border-line text-muted">
                {label} · {n}
              </span>
            ))}
          </div>
        ) : (
          <div className="font-mono text-[10px] text-faint">ничего не найдено</div>
        )}
      </div>

      {/* Lineage completeness + materialize */}
      <div className="rounded border border-line/60 bg-surface/40 p-2.5">
        <div className="flex items-center justify-between font-mono text-[11px]">
          <span className="text-faint">
            EXTRACTED_BY: <span className="text-nickel">{detail.evidence_by_edge}</span> /{' '}
            {detail.evidence_by_prop} Evidence
          </span>
          {!detail.lineage_complete && canWrite() && (
            <button
              onClick={onMaterialize}
              disabled={materializing}
              className="inline-flex items-center gap-1 rounded border border-copper/50 px-2 py-1 text-[10px] text-copper transition-colors hover:bg-copper/10 disabled:opacity-50"
            >
              {materializing ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <Wrench size={11} />
              )}
              достроить рёбра
            </button>
          )}
        </div>
        {result && (
          <div className="mt-1.5 font-mono text-[10px] text-verified">
            создано {result.edges_created} рёбер · всего {result.edges_after}/
            {result.evidence_by_prop}
            {result.lineage_complete ? ' · lineage полон' : ''}
          </div>
        )}
        {detail.evidence_sample.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {detail.evidence_sample.map((id) => (
              <span
                key={id}
                className="max-w-full truncate rounded bg-surface/60 px-1.5 py-0.5 font-mono text-[9px] text-faint"
                title={id}
              >
                {id}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EvidenceLookup({
  query,
  onQuery,
  onSubmit,
  loading,
  result,
  error,
}: {
  query: string;
  onQuery: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  result?: EvidenceLineage;
  error: boolean;
}) {
  return (
    <div className="panel p-4">
      <div className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
        <FileSearch size={12} className="text-copper" /> lineage одного Evidence
      </div>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          placeholder="Evidence id…"
          className="min-w-0 flex-1 rounded border border-line bg-surface/60 px-2 py-1 font-mono text-[11px] text-nickel outline-none focus:border-copper/60"
        />
        <button
          onClick={onSubmit}
          className="inline-flex items-center gap-1 rounded border border-line px-2 py-1 text-[11px] text-muted transition-colors hover:border-copper/60 hover:text-copper"
        >
          <Search size={12} /> найти
        </button>
      </div>

      {loading ? (
        <div className="mt-2 flex items-center gap-2 font-mono text-[11px] text-faint">
          <Loader2 size={12} className="animate-spin text-copper" /> поиск…
        </div>
      ) : error ? (
        <div className="mt-2 text-[11px] text-contradiction">Ошибка запроса.</div>
      ) : result ? (
        !result.found ? (
          <div className="mt-2 font-mono text-[11px] text-faint">Evidence не найден в графе.</div>
        ) : !result.run_id ? (
          <div className="mt-2 font-mono text-[11px] text-gap">
            Evidence найден, но не привязан к прогону (нет ни ребра, ни extractor_run_id).
          </div>
        ) : (
          <div className="mt-2 space-y-1">
            <div className="flex items-center gap-2 font-mono text-[11px]">
              <span className="text-faint">прогон:</span>
              <span className="text-nickel">{result.run_id}</span>
              <span
                className={`chip ${
                  result.linked_via === 'edge'
                    ? 'text-verified border-verified/40'
                    : 'text-gap border-gap/40'
                }`}
              >
                {result.linked_via === 'edge' ? (
                  <>
                    <Link2 size={10} /> ребро EXTRACTED_BY
                  </>
                ) : (
                  <>
                    <Link2Off size={10} /> только свойство
                  </>
                )}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[10px] text-muted">
              {result.model && (
                <span className="inline-flex items-center gap-1">
                  <Cpu size={10} /> {result.model}
                </span>
              )}
              {result.extractor && <span>extractor {result.extractor}</span>}
              {result.pipeline_version && <span>pipeline {result.pipeline_version}</span>}
              {result.schema_version && <span>schema {result.schema_version}</span>}
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
