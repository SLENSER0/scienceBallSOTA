import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  Check,
  CircleDashed,
  Database,
  FileSearch,
  Loader2,
  Save,
  Scissors,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

// §5.10 «Живой Dagster-оркестратор ingestion»: загрузка документа запускает
// реальный конвейер приёма (register→parse→store→chunk→extract) в фоновом потоке
// на сервере, а этот экран polling-ом рисует пер-стадийный прогресс — наглядная
// демонстрация настоящего конвейера, а не чёрного ящика. Бэкенд:
// POST /api/v1/ingest/pipeline/upload → GET /api/v1/ingest/pipeline/{run_id}.

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.txt,.md';
const POLL_MS = 800;

type StageStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled';

interface StageRun {
  op: string;
  label: string;
  status: StageStatus;
  started_at: string | null;
  finished_at: string | null;
  detail: Record<string, unknown>;
  error: string | null;
}
interface PipelineRun {
  run_id: string;
  filename: string;
  status: 'running' | 'succeeded' | 'failed' | 'cancelled';
  created_at: string;
  updated_at: string;
  doc_id: string | null;
  source_id: string | null;
  progress: number;
  stages: StageRun[];
  error: string | null;
}

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

const OP_ICON: Record<string, typeof Database> = {
  register_source: Database,
  parse: FileSearch,
  store: Save,
  chunk: Scissors,
  extract: Sparkles,
};

function StatusBadge({ status }: { status: StageStatus }) {
  const map: Record<StageStatus, { icon: JSX.Element; cls: string; text: string }> = {
    pending: { icon: <CircleDashed className="h-4 w-4" />, cls: 'text-faint', text: 'ожидает' },
    running: { icon: <Loader2 className="h-4 w-4 animate-spin" />, cls: 'text-sky-400', text: 'выполняется' },
    succeeded: { icon: <Check className="h-4 w-4" />, cls: 'text-emerald-400', text: 'готово' },
    skipped: { icon: <Check className="h-4 w-4" />, cls: 'text-amber-400', text: 'пропущено' },
    failed: { icon: <AlertTriangle className="h-4 w-4" />, cls: 'text-rose-400', text: 'ошибка' },
    cancelled: { icon: <Ban className="h-4 w-4" />, cls: 'text-faint', text: 'отменено' },
  };
  const m = map[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${m.cls}`}>
      {m.icon}
      {m.text}
    </span>
  );
}

function elapsed(a: string | null, b: string | null): string {
  if (!a) return '';
  const start = Date.parse(a);
  const end = b ? Date.parse(b) : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return '';
  const ms = Math.max(0, end - start);
  return ms < 1000 ? `${ms} мс` : `${(ms / 1000).toFixed(1)} с`;
}

function detailChips(d: Record<string, unknown>): string[] {
  const skip = new Set(['sha1', 'sidecar', 'source_id', 'doc_id', 'status']);
  const out: string[] = [];
  for (const [k, v] of Object.entries(d)) {
    if (skip.has(k) || v === null || v === undefined || v === '') continue;
    out.push(`${k}: ${v}`);
  }
  return out;
}

function StageRow({ stage }: { stage: StageRun }) {
  const Icon = OP_ICON[stage.op] ?? CircleDashed;
  const active = stage.status === 'running';
  const done = stage.status === 'succeeded' || stage.status === 'skipped';
  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-3 transition-colors ${
        active
          ? 'border-sky-500/50 bg-sky-500/5'
          : done
            ? 'border-emerald-500/30 bg-emerald-500/5'
            : stage.status === 'failed'
              ? 'border-rose-500/40 bg-rose-500/5'
              : 'border-line bg-raised/40'
      }`}
    >
      <div
        className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full ${
          active ? 'bg-sky-500/20 text-sky-300' : done ? 'bg-emerald-500/20 text-emerald-300' : 'bg-raised text-faint'
        }`}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm font-medium">{stage.label}</span>
          <StatusBadge status={stage.status} />
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-faint">
          {(stage.status === 'running' || stage.finished_at) && (
            <span className="tabular-nums">{elapsed(stage.started_at, stage.finished_at)}</span>
          )}
          {detailChips(stage.detail).map((c) => (
            <span key={c} className="rounded bg-raised px-1.5 py-0.5 tabular-nums">
              {c}
            </span>
          ))}
        </div>
        {stage.error && <p className="mt-1 text-xs text-rose-400">{stage.error}</p>}
      </div>
    </div>
  );
}

export function IngestPipelineView() {
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const poll = useCallback(
    async (runId: string) => {
      try {
        const res = await fetch(`/api/v1/ingest/pipeline/${encodeURIComponent(runId)}`, {
          headers: { ...authHeaders() },
        });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const data: PipelineRun = await res.json();
        setRun(data);
        if (data.status === 'running') {
          timer.current = setTimeout(() => void poll(runId), POLL_MS);
        }
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
      }
    },
    [],
  );

  useEffect(() => stopPolling, [stopPolling]);

  const start = useCallback(
    async (file: File) => {
      stopPolling();
      setBusy(true);
      setError('');
      setRun(null);
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch('/api/v1/ingest/pipeline/upload', {
          method: 'POST',
          headers: { ...authHeaders() },
          body: form,
        });
        if (!res.ok) {
          const txt = await res.text().catch(() => '');
          throw new Error(`${res.status} ${res.statusText}${txt ? ` — ${txt}` : ''}`);
        }
        const data: PipelineRun = await res.json();
        setRun(data);
        if (data.status === 'running') timer.current = setTimeout(() => void poll(data.run_id), POLL_MS);
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
      } finally {
        setBusy(false);
      }
    },
    [poll, stopPolling],
  );

  const cancel = useCallback(async () => {
    if (!run) return;
    try {
      await fetch(`/api/v1/ingest/pipeline/${encodeURIComponent(run.run_id)}/cancel`, {
        method: 'POST',
        headers: { ...authHeaders() },
      });
    } catch {
      /* поллинг покажет финальный статус */
    }
  }, [run]);

  const onFile = (f: File | null | undefined) => {
    if (f) void start(f);
  };

  const pct = run ? Math.round(run.progress * 100) : 0;
  const running = run?.status === 'running';

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-5">
      <header>
        <h1 className="flex items-center gap-2 text-lg font-semibold">
          <UploadCloud className="h-5 w-5 text-sky-400" />
          Конвейер приёма — живой статус этапов
        </h1>
        <p className="mt-1 text-sm text-faint">
          Загрузите документ — сервер прогонит реальный конвейер приёма
          (<span className="text-ink">регистрация → разбор → сохранение → чанкинг → извлечение</span>) в
          фоне, а здесь видно статус каждой стадии в реальном времени (§5.10).
        </p>
      </header>

      {/* drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          onFile(e.dataTransfer.files?.[0]);
        }}
        onClick={() => inputRef.current?.click()}
        className={`grid cursor-pointer place-items-center rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          drag ? 'border-sky-400 bg-sky-500/10' : 'border-line bg-raised/40 hover:border-sky-500/50'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])}
        />
        {busy ? (
          <span className="inline-flex items-center gap-2 text-sm text-faint">
            <Loader2 className="h-4 w-4 animate-spin" /> Загрузка…
          </span>
        ) : (
          <div className="space-y-1">
            <UploadCloud className="mx-auto h-7 w-7 text-faint" />
            <p className="text-sm font-medium">Перетащите файл сюда или нажмите</p>
            <p className="text-xs text-faint">PDF · DOCX · PPTX · XLSX · TXT · MD (до 64 МБ)</p>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="break-words">{error}</span>
        </div>
      )}

      {run && (
        <section className="space-y-4 rounded-xl border border-line bg-raised/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{run.filename}</p>
              <p className="text-xs text-faint">
                run_id: <span className="tabular-nums">{run.run_id}</span>
                {run.doc_id && <> · doc: <span className="tabular-nums">{run.doc_id}</span></>}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={run.status as StageStatus} />
              {running && (
                <button
                  onClick={() => void cancel()}
                  className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-faint hover:border-rose-500/50 hover:text-rose-300"
                >
                  <Ban className="h-3.5 w-3.5" /> Отменить
                </button>
              )}
            </div>
          </div>

          {/* aggregate progress bar */}
          <div>
            <div className="mb-1 flex justify-between text-xs text-faint">
              <span>Общий прогресс</span>
              <span className="tabular-nums">{pct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-raised">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  run.status === 'failed'
                    ? 'bg-rose-500'
                    : run.status === 'cancelled'
                      ? 'bg-zinc-500'
                      : 'bg-emerald-500'
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          {/* per-stage ladder */}
          <div className="space-y-2">
            {run.stages.map((s) => (
              <StageRow key={s.op} stage={s} />
            ))}
          </div>

          {run.error && run.status === 'failed' && (
            <p className="text-xs text-rose-400">Конвейер остановлен: {run.error}</p>
          )}
        </section>
      )}
    </div>
  );
}
