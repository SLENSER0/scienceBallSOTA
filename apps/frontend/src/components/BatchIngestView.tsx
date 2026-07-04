import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  FileStack,
  FolderInput,
  Gauge,
  Loader2,
  Play,
  UploadCloud,
  XCircle,
} from 'lucide-react';

// §5.10 «Batch/bulk-ингест директории с агрегированным отчётом». Drop 20–50
// документов (или прогнать server-side каталог) → один пакетный прогон через
// настоящий per-doc конвейер → живой агрегированный отчёт: готово / дубликаты /
// ошибки, извлечённые чанки·сущности·факты и пропускная способность (docs/min).
// Задача фоновая: старт возвращает job_id, дальше опрашиваем /report/{job_id}.

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.xls,.txt,.md';

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

interface DocResult {
  doc_id: string | null;
  title: string;
  status: string;
  duplicate?: boolean;
  chunks?: number;
  error?: string;
}
interface BatchReport {
  job: { job_id: string; status: string; progress: number; total: number; done: number };
  report: {
    total: number;
    done: number;
    failed: number;
    duplicates: number;
    by_status: Record<string, number>;
    failures: { doc_id: string | null; error: string }[];
  };
  extraction: Record<string, number | Record<string, number>>;
  results: DocResult[];
  throughput: { processed: number; total: number; elapsed_s: number; docs_per_min: number };
  use_llm: boolean;
  source: string;
}

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);

function Stat({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: string | number;
  tone?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface/40 px-4 py-3">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-faint">
        {icon}
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone ?? 'text-nickel'}`}>{value}</div>
    </div>
  );
}

export function BatchIngestView() {
  const qc = useQueryClient();
  const [drag, setDrag] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [useLlm, setUseLlm] = useState(false);
  const [dataDir, setDataDir] = useState('');
  const [dirLimit, setDirLimit] = useState(30);
  const [jobId, setJobId] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(
    (id: string) => {
      stopPolling();
      const tick = async () => {
        try {
          const res = await fetch(`/api/v1/batch-ingest/report/${encodeURIComponent(id)}`, {
            headers: { ...authHeaders() },
          });
          if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
          const data: BatchReport = await res.json();
          setReport(data);
          if (TERMINAL.has(data.job.status)) {
            stopPolling();
            setBusy(false);
            void qc.invalidateQueries({ queryKey: ['coverage'] });
            void qc.invalidateQueries({ queryKey: ['graph'] });
            void qc.invalidateQueries({ queryKey: ['recent-articles'] });
          }
        } catch (e) {
          setError(String(e instanceof Error ? e.message : e));
        }
      };
      void tick();
      pollRef.current = window.setInterval(tick, 1500);
    },
    [qc, stopPolling],
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  const startUpload = useCallback(async () => {
    if (!files.length) return;
    setBusy(true);
    setError('');
    setReport(null);
    try {
      const form = new FormData();
      for (const f of files) form.append('files', f);
      const res = await fetch(`/api/v1/batch-ingest/upload?use_llm=${useLlm}`, {
        method: 'POST',
        headers: { ...authHeaders() },
        body: form,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setJobId(data.job_id);
      poll(data.job_id);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setBusy(false);
    }
  }, [files, useLlm, poll]);

  const startDirectory = useCallback(async () => {
    setBusy(true);
    setError('');
    setReport(null);
    try {
      const res = await fetch('/api/v1/batch-ingest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ data_dir: dataDir || null, limit: dirLimit, use_llm: useLlm }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setJobId(data.job_id);
      poll(data.job_id);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setBusy(false);
    }
  }, [dataDir, dirLimit, useLlm, poll]);

  const cancel = useCallback(async () => {
    if (!jobId) return;
    try {
      await fetch(`/api/v1/batch-ingest/cancel/${encodeURIComponent(jobId)}`, {
        method: 'POST',
        headers: { ...authHeaders() },
      });
    } catch {
      /* ignore */
    }
  }, [jobId]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (dropped.length) setFiles((prev) => [...prev, ...dropped]);
  };

  const ex = report?.extraction ?? {};
  const num = (k: string): number => (typeof ex[k] === 'number' ? (ex[k] as number) : 0);
  const byLabel = (ex['by_label'] as Record<string, number> | undefined) ?? {};

  return (
    <div className="h-full overflow-y-auto">
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-lg font-semibold text-nickel">
          <FileStack size={20} className="text-copper" />
          Пакетная загрузка · агрегированный отчёт
        </div>
        <p className="mt-1 max-w-3xl text-sm text-faint">
          Перетащите 20–50 документов или запустите прогон по каталогу на сервере. Весь набор проходит
          через настоящий per-doc конвейер (§5.10), а результаты сворачиваются в одну сводку: готово,
          дубликаты, ошибки, извлечённые факты и пропускная способность.
        </p>
      </div>

      <div className="grid gap-5 p-6 lg:grid-cols-2">
        {/* -- Drop 20–50 files ------------------------------------------- */}
        <div className="panel p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-nickel">
            <UploadCloud size={15} className="text-copper" /> Вариант A — перетащить документы
          </div>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-4 py-8 text-center transition ${
              drag ? 'border-copper bg-copper/10' : 'border-line hover:border-copper/50'
            } ${busy ? 'pointer-events-none opacity-60' : ''}`}
          >
            <UploadCloud size={22} className="text-faint" />
            <div className="text-sm text-nickel">Перетащите файлы или нажмите, чтобы выбрать</div>
            <div className="font-mono text-[10px] text-faint">PDF · DOCX · PPTX · XLSX · TXT · MD · до 60 файлов</div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                const chosen = Array.from(e.target.files ?? []);
                if (chosen.length) setFiles((prev) => [...prev, ...chosen]);
              }}
            />
          </div>
          {files.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between text-xs text-faint">
                <span>{files.length} файл(ов) выбрано</span>
                <button className="text-copper hover:underline" onClick={() => setFiles([])} disabled={busy}>
                  очистить
                </button>
              </div>
              <div className="max-h-28 overflow-y-auto rounded-md border border-line bg-surface/30 p-2 font-mono text-[11px] text-faint">
                {files.map((f, i) => (
                  <div key={i} className="truncate">
                    {f.name} · {(f.size / 1024).toFixed(0)} КБ
                  </div>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={startUpload}
            disabled={busy || !files.length}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-copper/40 bg-copper/15 px-4 py-2 text-sm font-medium text-copper transition hover:bg-copper/25 disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            Запустить пакетный прогон
          </button>
        </div>

        {/* -- Server-side directory ------------------------------------- */}
        <div className="panel p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-nickel">
            <FolderInput size={15} className="text-copper" /> Вариант B — каталог на сервере
          </div>
          <label className="mb-1 block text-xs text-faint">Путь к каталогу (пусто → seed-корпус)</label>
          <input
            value={dataDir}
            onChange={(e) => setDataDir(e.target.value)}
            placeholder="data/ (по умолчанию)"
            disabled={busy}
            className="w-full rounded-md border border-line bg-surface/50 px-3 py-2 font-mono text-xs text-nickel outline-none focus:border-copper/50"
          />
          <label className="mb-1 mt-3 block text-xs text-faint">Максимум файлов: {dirLimit}</label>
          <input
            type="range"
            min={5}
            max={60}
            step={5}
            value={dirLimit}
            onChange={(e) => setDirLimit(Number(e.target.value))}
            disabled={busy}
            className="w-full accent-copper"
          />
          <button
            onClick={startDirectory}
            disabled={busy}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-copper/40 bg-copper/15 px-4 py-2 text-sm font-medium text-copper transition hover:bg-copper/25 disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            Прогнать каталог
          </button>

          <label className="mt-4 flex items-center gap-2 text-xs text-faint">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              disabled={busy}
              className="accent-copper"
            />
            LLM-обогащение (медленнее, до 3 чанков/док)
          </label>
        </div>
      </div>

      {error && (
        <div className="mx-6 mb-4 flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      {/* -- Aggregated report ------------------------------------------- */}
      {report && (
        <div className="px-6 pb-8">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium text-nickel">Агрегированный отчёт</span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                report.job.status === 'succeeded'
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : report.job.status === 'running'
                    ? 'bg-copper/15 text-copper'
                    : report.job.status === 'cancelled'
                      ? 'bg-amber-500/15 text-amber-400'
                      : 'bg-red-500/15 text-red-400'
              }`}
            >
              {report.job.status}
            </span>
            <span className="font-mono text-xs text-faint">{report.job.job_id}</span>
            {report.job.status === 'running' && (
              <button onClick={cancel} className="ml-auto text-xs text-amber-400 hover:underline">
                отменить
              </button>
            )}
          </div>

          {/* progress bar */}
          <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-surface/60">
            <div
              className="h-full rounded-full bg-copper transition-all"
              style={{ width: `${Math.round((report.job.progress || 0) * 100)}%` }}
            />
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Всего" value={report.report.total} icon={<FileStack size={12} />} />
            <Stat label="Готово" value={report.report.done} tone="text-emerald-400" icon={<CheckCircle2 size={12} />} />
            <Stat label="Дубликаты" value={report.report.duplicates} tone="text-sky-400" icon={<Copy size={12} />} />
            <Stat label="Ошибки" value={report.report.failed} tone="text-red-400" icon={<XCircle size={12} />} />
            <Stat
              label="docs/min"
              value={report.throughput.docs_per_min}
              tone="text-copper"
              icon={<Gauge size={12} />}
            />
            <Stat label="Время, с" value={report.throughput.elapsed_s} icon={<Gauge size={12} />} />
          </div>

          {/* extraction tally */}
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Чанки" value={num('chunks')} />
            <Stat label="Сущности" value={num('entities')} />
            <Stat label="Измерения" value={num('measurements')} />
            <Stat label="Evidence" value={num('evidence')} />
          </div>

          {Object.keys(byLabel).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(byLabel)
                .sort((a, b) => b[1] - a[1])
                .map(([label, n]) => (
                  <span
                    key={label}
                    className="rounded-full border border-line bg-surface/40 px-2.5 py-0.5 text-xs text-faint"
                  >
                    {label}: <span className="font-mono text-nickel">{n}</span>
                  </span>
                ))}
            </div>
          )}

          {/* per-doc results */}
          <div className="mt-5 overflow-x-auto rounded-lg border border-line">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-faint">
                  <th className="px-3 py-2">Документ</th>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2 text-right">Чанки</th>
                  <th className="px-3 py-2">Примечание</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map((r, i) => (
                  <tr key={i} className="border-b border-line/50 last:border-0">
                    <td className="max-w-[280px] truncate px-3 py-2 text-nickel" title={r.title}>
                      {r.title}
                    </td>
                    <td className="px-3 py-2">
                      {r.status === 'failed' ? (
                        <span className="inline-flex items-center gap-1 text-red-400">
                          <XCircle size={13} /> ошибка
                        </span>
                      ) : r.duplicate ? (
                        <span className="inline-flex items-center gap-1 text-sky-400">
                          <Copy size={13} /> дубликат
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-emerald-400">
                          <CheckCircle2 size={13} /> готово
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-faint">{r.chunks ?? '—'}</td>
                    <td className="max-w-[240px] truncate px-3 py-2 text-xs text-faint" title={r.error}>
                      {r.error ?? ''}
                    </td>
                  </tr>
                ))}
                {report.results.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-sm text-faint">
                      Ожидание первых результатов…
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
