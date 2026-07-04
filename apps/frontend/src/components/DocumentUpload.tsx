import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  Network,
  RefreshCw,
  UploadCloud,
} from 'lucide-react';
import { api, type UploadResult } from '../api';
import { GraphPanel } from './GraphPanel';

// Upload PDF → граф → viewer (§17.19). Drop a document, run the real ingestion
// pipeline server-side, then render the freshly ingested subgraph (2D/3D) beside a
// paged parsed-document viewer. On success the graph/coverage query caches are
// invalidated so the rest of the app reflects the new document (§23 acceptance).

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.txt,.md';

export function DocumentUpload() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState<UploadResult | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const run = useCallback(
    async (file: File) => {
      setBusy(true);
      setError('');
      setResult(null);
      setPhase(`Загрузка «${file.name}» → парсинг → извлечение графа…`);
      try {
        const res = await api.uploadDocument(file, false);
        setResult(res);
        setPhase('');
        // §23: a new document must refresh graph, indexes and coverage dashboards.
        void qc.invalidateQueries({ queryKey: ['coverage'] });
        void qc.invalidateQueries({ queryKey: ['graph'] });
        void qc.invalidateQueries({ queryKey: ['recent-articles'] });
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
        setPhase('');
      } finally {
        setBusy(false);
      }
    },
    [qc],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) void run(f);
  };

  return (
    <div className="panel mt-5 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
        <UploadCloud size={15} className="text-copper" /> Загрузить документ → граф
      </div>

      {/* Dropzone */}
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
        {busy ? (
          <Loader2 size={22} className="animate-spin text-copper" />
        ) : (
          <UploadCloud size={22} className="text-faint" />
        )}
        <div className="text-sm text-nickel">
          {busy ? phase : 'Перетащите файл или нажмите, чтобы выбрать'}
        </div>
        <div className="font-mono text-[10px] text-faint">PDF · DOCX · PPTX · XLSX · TXT · MD (до 64 МБ)</div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void run(f);
            e.target.value = '';
          }}
        />
      </div>

      {error && (
        <div className="mt-3 rounded border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
          Ошибка загрузки: {error}
        </div>
      )}

      {result && <UploadResultView result={result} qc={qc} />}
    </div>
  );
}

function UploadResultView({
  result,
  qc,
}: {
  result: UploadResult;
  qc: ReturnType<typeof useQueryClient>;
}) {
  const [reindexing, setReindexing] = useState(false);
  const [graph, setGraph] = useState(result.graph);
  const [nodeCount, setNodeCount] = useState(result.node_count);

  const reindex = async () => {
    setReindexing(true);
    try {
      const res = await api.reindexDocument(result.doc_id, false);
      setGraph(res.graph);
      setNodeCount(res.node_count);
      void qc.invalidateQueries({ queryKey: ['coverage'] });
      void qc.invalidateQueries({ queryKey: ['graph'] });
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div className="mt-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="chip text-verified border-verified/40">
          {result.status === 'skipped' ? 'уже в графе' : 'добавлено в граф'}
        </span>
        <span className="text-sm text-ink">{result.title}</span>
        <span className="font-mono text-[10px] text-faint">
          {result.page_count} стр · {result.chunks} чанков · {nodeCount} узлов
        </span>
        <button
          onClick={() => void reindex()}
          disabled={reindexing}
          className="chip ml-auto text-faint hover:border-copper/40 hover:text-copper disabled:opacity-50"
          title="Переиндексировать документ"
        >
          {reindexing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          Reindex
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Ingested subgraph — 2D/3D */}
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
            <Network size={12} /> граф документа
          </div>
          <div className="h-[360px] overflow-hidden rounded-md border border-line">
            {graph.nodes.length > 0 ? (
              <GraphPanel data={graph} />
            ) : (
              <div className="flex h-full items-center justify-center font-mono text-xs text-faint">
                граф пуст — сущности не извлечены
              </div>
            )}
          </div>
        </div>

        {/* Parsed document viewer */}
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
            <FileText size={12} /> parsed-просмотр
          </div>
          <DocumentViewer docId={result.doc_id} />
        </div>
      </div>
    </div>
  );
}

export function DocumentViewer({
  docId,
  initialPage,
  highlight,
}: {
  docId: string;
  initialPage?: number;
  highlight?: string;
}) {
  const [page, setPage] = useState(initialPage ?? 1);
  const [data, setData] = useState<{
    title: string;
    page_count: number;
    pages: { page: number; text: string }[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const markRef = useRef<HTMLElement | null>(null);

  // Load the parsed content whenever the document changes.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .documentParsed(docId)
      .then((d) => {
        if (alive) setData(d);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [docId]);

  // Jump to the page the evidence lives on (if it exists), else the first page.
  useEffect(() => {
    if (!data) return;
    const target =
      initialPage != null && data.pages.some((p) => p.page === initialPage)
        ? initialPage
        : data.pages[0]?.page ?? 1;
    setPage(target);
  }, [initialPage, data]);

  // Scroll the highlighted quote into view once the page/highlight resolves.
  useEffect(() => {
    if (markRef.current) markRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [page, highlight, data]);

  if (loading || !data) {
    return (
      <div className="flex h-[360px] items-center justify-center rounded-md border border-line font-mono text-xs text-faint">
        <Loader2 size={14} className="mr-2 animate-spin text-copper" /> загрузка…
      </div>
    );
  }

  const current = data.pages.find((p) => p.page === page) ?? data.pages[0];
  const total = data.page_count || data.pages.length;

  return (
    <div className="flex h-[360px] flex-col rounded-md border border-line">
      <div className="flex items-center justify-between border-b border-line px-3 py-1.5">
        <span className="truncate font-mono text-[10px] text-faint">{data.title}</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded p-1 text-faint hover:text-copper disabled:opacity-30"
          >
            <ChevronLeft size={13} />
          </button>
          <span className="font-mono text-[10px] text-nickel">
            {page} / {total}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(total, p + 1))}
            disabled={page >= total}
            className="rounded p-1 text-faint hover:text-copper disabled:opacity-30"
          >
            <ChevronRight size={13} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-3 py-2 text-[13px] leading-relaxed text-ink/90">
        {current?.text ? (
          renderHighlighted(current.text, highlight, markRef)
        ) : (
          <span className="text-faint">пустая страница</span>
        )}
      </div>
    </div>
  );
}

// Highlight the evidence quote within a page's text — whitespace-flexible and
// case-insensitive (the quote may differ from the parsed text only in spacing).
// Attaches a ref to the first match so the viewer can scroll it into view.
function renderHighlighted(
  text: string,
  query: string | undefined,
  markRef: React.MutableRefObject<HTMLElement | null>,
): React.ReactNode {
  markRef.current = null;
  if (!query || !query.trim()) return text;
  const toRe = (q: string): RegExp | null => {
    const esc = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
    try {
      return new RegExp(esc, 'i');
    } catch {
      return null;
    }
  };
  const clean = query.trim();
  let m: RegExpExecArray | null = null;
  for (const q of [clean.slice(0, 200), clean.slice(0, 40)]) {
    const re = toRe(q);
    m = re ? re.exec(text) : null;
    if (m) break;
  }
  if (!m) return text;
  const start = m.index;
  const end = start + m[0].length;
  return (
    <>
      {text.slice(0, start)}
      <mark
        ref={(el) => {
          markRef.current = el;
        }}
        className="rounded bg-copper/40 px-0.5 text-ink"
      >
        {text.slice(start, end)}
      </mark>
      {text.slice(end)}
    </>
  );
}
