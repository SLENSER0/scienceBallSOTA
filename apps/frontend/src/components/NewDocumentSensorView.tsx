import { useCallback, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Activity,
  CircleCheck,
  Copy,
  FileUp,
  FolderInput,
  Loader2,
  Play,
  Power,
  PowerOff,
  RotateCcw,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';

// §9.6 new_document_sensor UI — «кинул PDF в папку → граф сам вырос».
// Self-contained (no api.ts edits): calls the new-document-sensor router directly
// with the same session-auth convention as api.ts.

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

async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as { detail?: string }).detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

interface PendingFile {
  file: string;
  token: string;
  size: number;
}
interface SensorEvent {
  kind: string;
  at: number;
  file?: string;
  status?: string;
  doc_id?: string | null;
  nodes_added?: number;
  rels_added?: number;
  by?: string;
  size?: number;
}
interface GraphCounts {
  nodes: number;
  rels: number;
}
interface Status {
  sensor: string;
  job_name: string;
  enabled: boolean;
  watched_dir: string;
  cursor: { name: string; position: string; seen_count: number };
  files_present: number;
  pending: PendingFile[];
  pending_count: number;
  graph: GraphCounts;
  recent_events: SensorEvent[];
}
interface PollResult extends Status {
  triggered: boolean;
  reason?: string;
  processed?: number;
  results?: {
    file: string;
    doc_id: string | null;
    title?: string;
    status: string;
    chunks?: number;
    nodes_added?: number;
    rels_added?: number;
    error?: string;
  }[];
  run_requests?: { run_key: string; job_name: string; partition_key: string | null }[];
  graph_before?: GraphCounts;
  graph_after?: GraphCounts;
  graph_growth?: GraphCounts;
}

const STATUS_STYLE: Record<string, string> = {
  ingested: 'text-emerald-400',
  duplicate: 'text-amber-400',
  failed: 'text-red-400',
};
const STATUS_LABEL: Record<string, string> = {
  ingested: 'в граф',
  duplicate: 'дубликат',
  failed: 'ошибка',
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} Б`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} КБ`;
  return `${(n / 1024 / 1024).toFixed(1)} МБ`;
}
function fmtTime(t: number): string {
  return new Date(t * 1000).toLocaleTimeString();
}

export function NewDocumentSensorView() {
  const [result, setResult] = useState<PollResult | null>(null);
  const [uploadErr, setUploadErr] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const status = useQuery({
    queryKey: ['nds-status'],
    queryFn: () => apiGet<Status>('/api/v1/new-document-sensor/status'),
    refetchInterval: 4000,
  });

  const poll = useMutation({
    mutationFn: () => apiPost<PollResult>('/api/v1/new-document-sensor/poll', { use_llm: false }),
    onSuccess: (d) => {
      setResult(d);
      status.refetch();
    },
  });

  const toggle = useMutation({
    mutationFn: (on: boolean) =>
      apiPost<Status>(`/api/v1/new-document-sensor/${on ? 'enable' : 'disable'}`),
    onSuccess: () => status.refetch(),
  });

  const reset = useMutation({
    mutationFn: () => apiPost<Status>('/api/v1/new-document-sensor/reset'),
    onSuccess: () => {
      setResult(null);
      status.refetch();
    },
  });

  const onUpload = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      setUploading(true);
      setUploadErr('');
      try {
        for (const f of Array.from(files)) {
          const form = new FormData();
          form.append('file', f);
          const res = await fetch('/api/v1/new-document-sensor/upload', {
            method: 'POST',
            headers: { ...authHeaders() },
            body: form,
          });
          if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            throw new Error((d as { detail?: string }).detail || `${res.status} ${res.statusText}`);
          }
        }
        await status.refetch();
      } catch (e) {
        setUploadErr(String(e instanceof Error ? e.message : e));
      } finally {
        setUploading(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    },
    [status],
  );

  const s = status.data;
  const enabled = s?.enabled ?? true;
  const growth = result?.graph_growth;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">new_document_sensor · §9.6</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Сенсор новых документов → граф растёт вживую
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Кинул документ в папку <span className="font-mono text-ink">kg-raw</span> — сенсор ловит
          его на следующем тике, прогоняет через настоящий per-doc конвейер приёма (
          <span className="font-mono">full_ingestion_job</span>) и граф растёт на глазах. Идемпотентно:
          курсор-водяной-знак не переобрабатывает файл, а дедуп по content-hash не плодит узлы
          (повторный файл — «дубликат»). Ниже — папка наблюдения, ожидающие файлы, живые счётчики
          графа и прирост от последнего тика.
        </p>

        {/* Control row */}
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <button
            onClick={() => poll.mutate()}
            disabled={poll.isPending || !enabled}
            className="btn-copper flex items-center gap-2"
            title={enabled ? 'Опросить папку и запустить приём' : 'Сенсор выключен'}
          >
            {poll.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {poll.isPending ? 'Тик сенсора…' : 'Опросить сенсор'}
          </button>

          <label className="cursor-pointer flex items-center gap-2 rounded-md border border-line bg-surface/50 px-3 py-2 text-sm font-medium text-nickel transition hover:bg-surface/80 disabled:opacity-50">
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <FileUp size={16} />}
            Кинуть файл в kg-raw
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              accept=".pdf,.docx,.pptx,.xlsx,.xls,.txt,.md"
              onChange={(e) => onUpload(e.target.files)}
            />
          </label>

          <button
            onClick={() => toggle.mutate(!enabled)}
            disabled={toggle.isPending}
            className="flex items-center gap-2 rounded-md border border-line bg-surface/50 px-3 py-2 text-sm font-medium text-nickel transition hover:bg-surface/80 disabled:opacity-50"
          >
            {enabled ? <PowerOff size={15} /> : <Power size={15} />}
            {enabled ? 'Выключить' : 'Включить'}
          </button>

          <button
            onClick={() => reset.mutate()}
            disabled={reset.isPending}
            className="flex items-center gap-2 rounded-md border border-line bg-surface/50 px-3 py-2 text-sm font-medium text-nickel transition hover:bg-surface/80 disabled:opacity-50"
            title="Перемотать курсор — файлы снова станут ожидающими"
          >
            <RotateCcw size={15} /> Сброс курсора
          </button>

          <span
            className={`ml-auto inline-flex items-center gap-1.5 text-xs font-medium ${
              enabled ? 'text-emerald-400' : 'text-faint'
            }`}
          >
            <Activity size={13} /> {enabled ? 'сенсор активен' : 'сенсор выключен'}
          </span>
        </div>

        {uploadErr && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка загрузки: {uploadErr}
          </div>
        )}
        {poll.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка тика: {(poll.error as Error).message}
          </div>
        )}

        {/* Live counters */}
        {s && (
          <div className="mb-6 grid gap-3 sm:grid-cols-4">
            <div className="panel p-3">
              <div className="text-xs text-faint">Узлов в графе</div>
              <div className="mt-1 font-display text-2xl text-ink">
                {s.graph.nodes.toLocaleString()}
              </div>
              {growth && growth.nodes > 0 && (
                <div className="text-xs text-emerald-400">+{growth.nodes} за тик</div>
              )}
            </div>
            <div className="panel p-3">
              <div className="text-xs text-faint">Рёбер в графе</div>
              <div className="mt-1 font-display text-2xl text-ink">
                {s.graph.rels.toLocaleString()}
              </div>
              {growth && growth.rels > 0 && (
                <div className="text-xs text-emerald-400">+{growth.rels} за тик</div>
              )}
            </div>
            <div className="panel p-3">
              <div className="text-xs text-faint">Ожидают приёма</div>
              <div className="mt-1 font-display text-2xl text-ink">{s.pending_count}</div>
              <div className="text-xs text-faint">из {s.files_present} в папке</div>
            </div>
            <div className="panel p-3">
              <div className="text-xs text-faint">Обработано (курсор)</div>
              <div className="mt-1 font-display text-2xl text-ink">{s.cursor.seen_count}</div>
              <div className="text-xs text-faint">файлов всего</div>
            </div>
          </div>
        )}

        {/* Watched dir */}
        {s && (
          <div className="panel mb-6 flex items-center gap-2 p-3 text-sm">
            <FolderInput size={16} className="text-copper" />
            <span className="text-faint">Папка наблюдения:</span>
            <span className="font-mono text-ink">{s.watched_dir}</span>
            <button
              onClick={() => navigator.clipboard?.writeText(s.watched_dir)}
              className="ml-1 text-faint hover:text-ink"
              title="Скопировать путь"
            >
              <Copy size={13} />
            </button>
          </div>
        )}

        {/* Poll result: what grew */}
        {result && (
          <div className="mb-6">
            {result.triggered ? (
              <div className="panel border-emerald-500/40 p-4">
                <div className="mb-2 flex items-center gap-2 text-emerald-400">
                  <Sparkles size={18} />
                  <span className="font-display text-lg">
                    Граф вырос: +{growth?.nodes ?? 0} узлов · +{growth?.rels ?? 0} рёбер
                  </span>
                  <span className="text-sm text-faint">
                    ({result.graph_before?.nodes ?? 0} → {result.graph_after?.nodes ?? 0} узлов)
                  </span>
                </div>
                <div className="mb-3 text-xs text-faint">
                  Обработано файлов: {result.processed ?? 0} · эмитировано RunRequest на{' '}
                  <span className="font-mono">{s?.job_name}</span>: {result.run_requests?.length ?? 0}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                        <th className="px-3 py-2">Файл</th>
                        <th className="px-3 py-2">Статус</th>
                        <th className="px-3 py-2 text-right">+узлы</th>
                        <th className="px-3 py-2 text-right">+рёбра</th>
                        <th className="px-3 py-2 text-right">чанки</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result.results ?? []).map((r) => (
                        <tr key={r.file} className="border-b border-line/30">
                          <td className="px-3 py-2 text-ink">
                            {r.title || r.file}
                            {r.error && (
                              <span className="ml-2 text-xs text-red-400">{r.error}</span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`text-xs font-medium ${
                                STATUS_STYLE[r.status] ?? 'text-faint'
                              }`}
                            >
                              {STATUS_LABEL[r.status] ?? r.status}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-emerald-400">
                            {r.nodes_added ? `+${r.nodes_added}` : '—'}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-emerald-400">
                            {r.rels_added ? `+${r.rels_added}` : '—'}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-faint">
                            {r.chunks ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="panel flex items-center gap-2 p-3 text-sm text-faint">
                <CircleCheck size={16} /> Тик выполнен: {result.reason ?? 'нет новых файлов'} — граф
                без изменений.
              </div>
            )}
          </div>
        )}

        {/* Pending files */}
        {s && s.pending.length > 0 && (
          <div className="mb-6">
            <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
              <TriangleAlert size={16} className="text-amber-400" /> Ожидают приёма (
              {s.pending.length})
            </h3>
            <div className="panel divide-y divide-line/30 p-0">
              {s.pending.map((p) => (
                <div key={p.token} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span className="font-mono text-ink">{p.file}</span>
                  <span className="text-xs text-faint">{fmtBytes(p.size)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Event feed */}
        {s && s.recent_events.length > 0 && (
          <div>
            <h3 className="mb-2 font-display text-lg">Лента событий сенсора</h3>
            <div className="panel divide-y divide-line/30 p-0">
              {s.recent_events.map((e, i) => (
                <div
                  key={`${e.at}-${i}`}
                  className="flex items-center gap-3 px-3 py-2 text-sm"
                >
                  <span className="w-20 shrink-0 font-mono text-xs text-faint">
                    {fmtTime(e.at)}
                  </span>
                  <span className="w-24 shrink-0 text-xs uppercase text-faint">{e.kind}</span>
                  <span className="flex-1 text-ink">
                    {e.file ?? '—'}
                    {e.status && (
                      <span
                        className={`ml-2 text-xs ${STATUS_STYLE[e.status] ?? 'text-faint'}`}
                      >
                        {STATUS_LABEL[e.status] ?? e.status}
                      </span>
                    )}
                  </span>
                  {typeof e.nodes_added === 'number' && e.nodes_added > 0 && (
                    <span className="font-mono text-xs text-emerald-400">
                      +{e.nodes_added} узлов
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
