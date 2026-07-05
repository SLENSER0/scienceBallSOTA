import { useCallback, useEffect, useState } from 'react';
import {
  Download,
  ExternalLink,
  FileText,
  Library,
  Loader2,
  Plus,
  Search,
  X,
} from 'lucide-react';
import { useStore } from '../store';
import { DocumentViewer } from './DocumentUpload';

// «Витрина источников» — a browsable showcase of the corpus (papers + documents)
// living in the knowledge graph. Each source can be opened (external URL / DOI /
// in-app parsed viewer / focused in the graph) or downloaded (Markdown export of a
// parsed upload, or a plain-text citation card for a graph-only source). Fetches the
// new GET /api/v1/documents/corpus endpoint; downloads go through fetch (not <a href>)
// so the auth headers ride along.

interface CorpusSource {
  doc_id: string;
  title: string;
  doc_type: string; // "paper" | "document"
  year: number | null;
  country: string | null;
  practice_type: string | null;
  evidence_strength: string | null;
  domain: string | null;
  url: string | null;
  doi: string | null;
  authors: string[];
  has_parsed: boolean;
  chunk_count: number;
}

interface CorpusResponse {
  sources: CorpusSource[];
  count: number;
}

// Low-trust deep-research sources parked in the review queue (not yet in the graph).
interface PendingItem {
  id: string;
  source: { title?: string; url?: string; year?: number | null; doi?: string | null };
  trust?: { trust_tier?: string };
}
interface PendingResponse {
  items: PendingItem[];
}

// Inline auth (copied from EvidenceInspectorView.authHeaders): bearer token if we have
// one, else a role header, else nothing. Kept inline so api.ts stays untouched.
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

const COUNTRY: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};

type DocTypeFilter = 'all' | 'paper' | 'document';

const TYPE_CHIPS: { id: DocTypeFilter; label: string }[] = [
  { id: 'all', label: 'все' },
  { id: 'paper', label: 'paper' },
  { id: 'document', label: 'document' },
];

function filenameFromDisposition(cd: string | null, fallback: string): string {
  if (!cd) return fallback;
  // Handle filename*=UTF-8''… and plain filename="…".
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(cd);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].replace(/^"|"$/g, '').trim());
    } catch {
      /* fall through */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  if (plain?.[1]) return plain[1].trim();
  return fallback;
}

export function SourcesShowcaseView() {
  const setView = useStore((s) => s.setView);
  const setSelectedNode = useStore((s) => s.setSelectedNode);

  const [input, setInput] = useState('');
  const [docType, setDocType] = useState<DocTypeFilter>('all');
  const [sources, setSources] = useState<CorpusSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewerDoc, setViewerDoc] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [approving, setApproving] = useState<string | null>(null);

  const load = useCallback(async (q: string, dt: DocTypeFilter) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (q.trim()) params.set('q', q.trim());
      if (dt !== 'all') params.set('doc_type', dt);
      const res = await fetch(`/api/v1/documents/corpus?${params.toString()}`, {
        headers: { ...authHeaders() },
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = (await res.json()) as CorpusResponse;
      setSources(data.sources ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSources([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced fetch on query / filter change (also does the initial mount load).
  useEffect(() => {
    const t = setTimeout(() => void load(input, docType), 350);
    return () => clearTimeout(t);
  }, [input, docType, load]);

  // Deep-research sources held for review (below the trust bar) — surfaced so «загрузил
  // из рисёрча → вижу» holds even before a curator approves them into the graph.
  const loadPending = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/research/sources/pending', { headers: { ...authHeaders() } });
      if (!res.ok) return;
      const data = (await res.json()) as PendingResponse;
      setPending(data.items ?? []);
    } catch {
      /* pending is best-effort — never block the corpus list */
    }
  }, []);

  useEffect(() => {
    void loadPending();
  }, [loadPending]);

  // Approve a pending source → it is ingested into the graph as a :Paper and then shows
  // up in the main corpus list on the next fetch.
  const approve = async (id: string) => {
    setApproving(id);
    setDlError(null);
    try {
      const res = await fetch(`/api/v1/research/sources/${encodeURIComponent(id)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setPending((prev) => prev.filter((p) => p.id !== id));
      void load(input, docType); // the approved source is now a graph :Paper → refresh
    } catch (e) {
      setDlError(e instanceof Error ? e.message : String(e));
    } finally {
      setApproving(null);
    }
  };

  const open = (s: CorpusSource) => {
    if (s.url) {
      window.open(s.url, '_blank', 'noopener');
      return;
    }
    if (s.doi) {
      window.open(`https://doi.org/${s.doi}`, '_blank', 'noopener');
      return;
    }
    if (s.has_parsed || s.chunk_count > 0) {
      // Uploaded sidecar OR body text in the graph (:Chunk) → open the in-app viewer.
      setViewerDoc(s.doc_id);
      return;
    }
    // No link, no text → focus the source node in the graph explorer.
    setSelectedNode({ id: s.doc_id, label: s.title, type: s.doc_type });
    setView('graph-explore');
  };

  const download = async (s: CorpusSource) => {
    setDownloading(s.doc_id);
    setDlError(null);
    try {
      const res = await fetch(
        `/api/v1/documents/${encodeURIComponent(s.doc_id)}/download`,
        { headers: { ...authHeaders() } },
      );
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const filename = filenameFromDisposition(
        res.headers.get('Content-Disposition'),
        `${s.doc_id}.txt`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Defer revoke a tick — some browsers (Firefox) cancel a not-yet-started
      // download if the object URL is revoked synchronously on the click tick.
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (e) {
      setDlError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-1 flex items-center gap-2 text-sm text-nickel">
          <Library size={16} className="text-copper" /> Витрина источников корпуса
        </div>
        <p className="mb-4 text-sm text-faint">
          Статьи и документы графа знаний. Откройте источник (внешняя ссылка, DOI,
          разбор в приложении или узел графа) либо скачайте его: Markdown-экспорт для
          загруженных документов, карточку цитирования для остальных.
        </p>

        {/* Search + type filter */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[240px] flex-1">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
            />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void load(input, docType)}
              placeholder="поиск по названию источника"
              className="w-full rounded-md border border-line bg-surface/60 py-2 pl-9 pr-3 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
            />
          </div>
          <div className="flex gap-1.5">
            {TYPE_CHIPS.map((c) => (
              <button
                key={c.id}
                onClick={() => setDocType(c.id)}
                className={`chip ${
                  docType === c.id
                    ? 'border-copper/50 text-copper'
                    : 'border-line text-faint hover:text-nickel'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {dlError && (
          <div className="mt-3 rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
            Ошибка: {dlError}
          </div>
        )}

        {/* Body */}
        <div className="mt-5">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 font-mono text-xs text-faint">
              <Loader2 size={16} className="animate-spin text-copper" /> загрузка источников…
            </div>
          ) : error ? (
            <div className="rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
              {error}
            </div>
          ) : sources.length === 0 ? (
            <div className="py-16 text-center font-mono text-[11px] text-faint">
              источники не найдены — уточните запрос или загрузите документ
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {sources.map((s) => (
                <SourceCard
                  key={s.doc_id}
                  s={s}
                  onOpen={() => open(s)}
                  onDownload={() => void download(s)}
                  downloading={downloading === s.doc_id}
                />
              ))}
            </div>
          )}
        </div>

        {/* Из deep-research — ниже порога доверия, пока НЕ в графе; «Добавить» их ингестит */}
        {pending.length > 0 && (
          <div className="mt-8">
            <div className="mb-2 text-sm text-nickel">
              Из deep-research · ожидают одобрения ({pending.length})
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {pending.map((p) => (
                <PendingCard
                  key={p.id}
                  p={p}
                  onApprove={() => void approve(p.id)}
                  approving={approving === p.id}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* In-app parsed viewer (reuses the DocumentUpload viewer). */}
      {viewerDoc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/70 p-4"
          onClick={() => setViewerDoc(null)}
        >
          <div
            className="panel w-full max-w-3xl p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-nickel">
                <FileText size={15} className="text-copper" /> Разбор документа
              </div>
              <button
                onClick={() => setViewerDoc(null)}
                className="rounded p-1 text-faint hover:text-copper"
                title="Закрыть"
              >
                <X size={16} />
              </button>
            </div>
            <DocumentViewer docId={viewerDoc} />
          </div>
        </div>
      )}
    </div>
  );
}

function PendingCard({
  p,
  onApprove,
  approving,
}: {
  p: PendingItem;
  onApprove: () => void;
  approving: boolean;
}) {
  const src = p.source ?? {};
  const title = src.title || src.url || 'источник';
  const tier = p.trust?.trust_tier;
  return (
    <div className="panel flex flex-col border-gap/30 p-4">
      <div className="mb-2 flex items-start gap-2">
        <FileText size={15} className="mt-0.5 shrink-0 text-gap" />
        <div className="min-w-0 flex-1">
          <div className="line-clamp-3 text-sm text-ink">{title}</div>
        </div>
        <span
          className="chip shrink-0 border-gap/40 text-gap"
          title="ещё не в графе — доверие ниже порога, требуется одобрение"
        >
          на ревью
        </span>
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {src.year != null && <span className="chip text-faint">{src.year}</span>}
        {tier && <span className="chip text-faint">доверие: {tier}</span>}
      </div>
      <div className="mt-auto flex gap-1.5 pt-1">
        {src.url && (
          <button
            onClick={() => window.open(src.url as string, '_blank', 'noopener')}
            className="chip flex items-center gap-1 border-line text-nickel hover:text-copper"
            title="Открыть источник"
          >
            <ExternalLink size={12} /> Открыть
          </button>
        )}
        <button
          onClick={onApprove}
          disabled={approving}
          className="chip flex items-center gap-1 border-copper/40 text-copper hover:bg-copper/10 disabled:opacity-40"
          title="Добавить в граф корпуса"
        >
          {approving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          Добавить в граф
        </button>
      </div>
    </div>
  );
}

function SourceCard({
  s,
  onOpen,
  onDownload,
  downloading,
}: {
  s: CorpusSource;
  onOpen: () => void;
  onDownload: () => void;
  downloading: boolean;
}) {
  const country = s.country ? COUNTRY[s.country] ?? s.country : null;
  return (
    <div className="panel flex flex-col p-4">
      <div className="mb-2 flex items-start gap-2">
        <FileText size={15} className="mt-0.5 shrink-0 text-copper" />
        <div className="min-w-0 flex-1">
          <div className="line-clamp-3 text-sm text-ink">{s.title}</div>
        </div>
        <span className="chip shrink-0 text-faint">{s.doc_type}</span>
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {s.year != null && <span className="chip text-faint">{s.year}</span>}
        {country && <span className="chip text-faint">{country}</span>}
        {s.evidence_strength && (
          <span className="chip text-faint">{s.evidence_strength}</span>
        )}
        {s.domain && <span className="chip text-faint">{s.domain}</span>}
        {s.chunk_count > 0 && (
          <span className="chip text-copper">текст: {s.chunk_count} фрагм.</span>
        )}
        {s.has_parsed && <span className="chip text-copper">разобран</span>}
      </div>

      {s.authors.length > 0 && (
        <div className="mb-3 line-clamp-1 text-xs text-muted">
          {s.authors.join(', ')}
        </div>
      )}

      <div className="mt-auto flex gap-1.5 pt-1">
        <button
          onClick={onOpen}
          className="chip flex items-center gap-1 border-copper/40 text-copper hover:bg-copper/10"
          title="Открыть источник"
        >
          <ExternalLink size={12} /> Открыть
        </button>
        <button
          onClick={onDownload}
          disabled={downloading}
          className="chip flex items-center gap-1 border-line text-nickel hover:text-copper disabled:opacity-40"
          title="Скачать источник"
        >
          {downloading ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Download size={12} />
          )}
          Скачать
        </button>
      </div>
    </div>
  );
}
