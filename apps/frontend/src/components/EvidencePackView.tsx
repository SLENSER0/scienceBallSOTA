import { useState } from 'react';
import {
  CheckCircle2,
  Download,
  FileArchive,
  FileCode2,
  FileJson,
  FileText,
  Loader2,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { useStore } from '../store';

// §23.29 Reproducible Evidence Pack — экспорт ответа (JSON/HTML/PDF/ZIP) + replay.
// Standalone view: builds a verifiable pack from a question and lets the user
// re-run (replay) it on the same snapshot to confirm the answer reproduces.

type Fmt = 'zip' | 'html' | 'pdf' | 'json';

interface ManifestEntry {
  name: string;
  sha256: string;
  size: number;
}
interface PackJson {
  answer_id: string;
  manifest: { root_sha256: string; total_bytes: number; entries: ManifestEntry[] };
  provenance: Record<string, unknown>;
  answer_fingerprint: string;
  snapshot_id: string;
  replay_url: string;
}
interface ReplayReport {
  answer_id: string;
  reproduced: boolean;
  original_fingerprint: string;
  replay_fingerprint: string;
  original_snapshot: string;
  replay_snapshot: string;
  snapshot_changed: boolean;
  divergence?: string[];
  explanation?: string;
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

const REQUIRED_SLOTS = [
  'model_version',
  'prompt_version',
  'extractor_run_id',
  'graph_schema_version',
  'data_snapshot_version',
  'retrieval_scores',
];

const FORMATS: { id: Fmt; label: string; icon: typeof Download; hint: string }[] = [
  { id: 'zip', label: 'ZIP', icon: FileArchive, hint: 'Полный пакет: манифест + все файлы' },
  { id: 'html', label: 'HTML', icon: FileCode2, hint: 'Автономный отчёт (открыть/печать в PDF)' },
  { id: 'pdf', label: 'PDF', icon: FileText, hint: 'PDF-обложка с проверочными хешами' },
  { id: 'json', label: 'JSON', icon: FileJson, hint: 'Манифест + provenance для проверки' },
];

export function EvidencePackView() {
  const { role, useLlm } = useStore();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState<Fmt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<PackJson | null>(null);
  const [replay, setReplay] = useState<ReplayReport | null>(null);
  const [replaying, setReplaying] = useState(false);

  const body = (): string =>
    JSON.stringify({ query: q.trim(), role, use_llm: useLlm, geography: null });

  const exportPack = async (fmt: Fmt) => {
    if (!q.trim()) return;
    setBusy(fmt);
    setError(null);
    setReplay(null);
    try {
      const res = await fetch(`/api/v1/answers/evidence-pack?format=${fmt}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: body(),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const answerId = res.headers.get('X-Answer-Id');

      if (fmt === 'json') {
        const data = (await res.json()) as PackJson;
        setMeta(data);
      } else if (fmt === 'html') {
        const text = await res.text();
        const blob = new Blob([text], { type: 'text/html' });
        window.open(URL.createObjectURL(blob), '_blank');
        if (answerId) setMeta((m) => m ?? ({ answer_id: answerId } as PackJson));
      } else {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${answerId ?? 'evidence-pack'}.${fmt}`;
        a.click();
        URL.revokeObjectURL(url);
        if (answerId) setMeta((m) => m ?? ({ answer_id: answerId } as PackJson));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const runReplay = async () => {
    if (!meta?.answer_id) return;
    setReplaying(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/answers/${encodeURIComponent(meta.answer_id)}/replay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        // Send the original query as a fallback if the server registry was cleared.
        body: JSON.stringify({ query: q.trim(), role, use_llm: useLlm, geography: null }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setReplay((await res.json()) as ReplayReport);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReplaying(false);
    }
  };

  const provComplete =
    meta?.provenance &&
    REQUIRED_SLOTS.every((s) => {
      const v = (meta.provenance as Record<string, unknown>)[s];
      return v !== undefined && v !== null && !(Array.isArray(v) && v.length === 0) && v !== '';
    });

  return (
    <div className="mx-auto max-w-4xl px-6 py-6">
      <div className="mb-1 flex items-center gap-2">
        <ShieldCheck size={18} className="text-copper" />
        <h1 className="text-lg font-semibold text-ink">Доказательный пакет (Evidence Pack)</h1>
      </div>
      <p className="mb-5 text-sm text-muted">
        Экспорт воспроизводимого пакета по ответу: вопрос, ответ, таблицы, доказательства, citations,
        provenance (версии моделей/промпта/схемы/снимка) и криптографический манифест. Replay
        перезапускает запрос на том же снимке и подтверждает, что каждое число воспроизводится.
      </p>

      <textarea
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Введите вопрос для экспорта доказательного пакета…"
        rows={3}
        className="w-full resize-y rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
      />

      <div className="mt-3 flex flex-wrap gap-2">
        {FORMATS.map((f) => {
          const Icon = f.icon;
          return (
            <button
              key={f.id}
              onClick={() => void exportPack(f.id)}
              disabled={!q.trim() || busy !== null}
              title={f.hint}
              className="chip flex items-center gap-1.5 border-line text-nickel hover:border-copper/40 hover:text-copper disabled:opacity-40"
            >
              {busy === f.id ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />}
              {f.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
          Ошибка: {error}
        </div>
      )}

      {meta?.manifest && (
        <div className="mt-6 rounded-md border border-line bg-surface/40 p-4">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className="eyebrow">answer id</span>
            <span className="metric font-mono text-xs text-copper">{meta.answer_id}</span>
            {provComplete !== undefined && (
              <span
                className={`chip ${provComplete ? 'text-verified' : 'text-gap'}`}
                title="Полнота provenance (6 обязательных слотов)"
              >
                {provComplete ? 'provenance полное' : 'provenance неполное'}
              </span>
            )}
          </div>

          <div className="mb-3 text-xs text-muted">
            <div>
              <span className="text-faint">root sha256:</span>{' '}
              <span className="break-all font-mono text-nickel">{meta.manifest.root_sha256}</span>
            </div>
            <div>
              <span className="text-faint">snapshot:</span>{' '}
              <span className="font-mono text-nickel">{meta.snapshot_id}</span> ·{' '}
              <span className="text-faint">байт:</span> {meta.manifest.total_bytes}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  {['Файл', 'sha256', 'Байт'].map((h) => (
                    <th
                      key={h}
                      className="px-2 py-1 text-left font-mono text-[10px] uppercase tracking-wide text-faint"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {meta.manifest.entries.map((e) => (
                  <tr key={e.name} className="border-t border-line/50">
                    <td className="px-2 py-1 font-mono text-nickel">{e.name}</td>
                    <td className="px-2 py-1 font-mono text-faint" title={e.sha256}>
                      {e.sha256.slice(0, 24)}…
                    </td>
                    <td className="px-2 py-1 font-mono text-faint">{e.size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {meta?.answer_id && (
        <div className="mt-4">
          <button
            onClick={() => void runReplay()}
            disabled={replaying}
            className="chip flex items-center gap-1.5 border-copper/40 text-copper hover:bg-copper/10 disabled:opacity-40"
            title="Перезапустить запрос на том же снимке данных и сравнить"
          >
            {replaying ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            Replay · проверить воспроизводимость
          </button>
        </div>
      )}

      {replay && (
        <div
          className={`mt-4 rounded-md border p-4 ${
            replay.reproduced
              ? 'border-verified/40 bg-verified/10'
              : 'border-gap/40 bg-gap/10'
          }`}
        >
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            {replay.reproduced ? (
              <CheckCircle2 size={16} className="text-verified" />
            ) : (
              <XCircle size={16} className="text-gap" />
            )}
            {replay.reproduced
              ? 'Ответ воспроизведён — идентичный content-fingerprint'
              : 'Расхождение при replay'}
          </div>
          {!replay.reproduced && (
            <div className="space-y-1 text-xs text-muted">
              {replay.explanation && <p>{replay.explanation}</p>}
              {replay.divergence && replay.divergence.length > 0 && (
                <p>
                  <span className="text-faint">Разошлись поля:</span>{' '}
                  <span className="font-mono text-gap">{replay.divergence.join(', ')}</span>
                </p>
              )}
              <p>
                <span className="text-faint">snapshot изменился:</span>{' '}
                {replay.snapshot_changed ? 'да' : 'нет'}
              </p>
            </div>
          )}
          <div className="mt-2 font-mono text-[10px] text-faint">
            {replay.original_fingerprint.slice(0, 16)} → {replay.replay_fingerprint.slice(0, 16)}
          </div>
        </div>
      )}
    </div>
  );
}
