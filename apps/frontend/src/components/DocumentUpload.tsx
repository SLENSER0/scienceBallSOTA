import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Database,
  FileText,
  Loader2,
  Network,
  RefreshCw,
  UploadCloud,
  X,
} from 'lucide-react';
import { api, type UploadResult } from '../api';
import { GraphPanel } from './GraphPanel';

// Upload PDF → граф → viewer (§17.19). Drop a document, run the real ingestion
// pipeline server-side, then render the freshly ingested subgraph (2D/3D) beside a
// paged parsed-document viewer. On success the graph/coverage query caches are
// invalidated so the rest of the app reflects the new document (§23 acceptance).

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.txt,.md';

type QueueItem = {
  id: string;
  name: string;
  status: 'uploading' | 'done' | 'skipped' | 'error';
  result?: UploadResult;
  error?: string;
};

export function DocumentUpload() {
  const qc = useQueryClient();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const run = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        const id = `${file.name}-${queueKey()}`;
        setQueue((q) => [{ id, name: file.name, status: 'uploading' }, ...q]);
        try {
          const res = await api.uploadDocument(file, false);
          setQueue((q) =>
            q.map((it) =>
              it.id === id
                ? { ...it, status: res.status === 'skipped' ? 'skipped' : 'done', result: res }
                : it,
            ),
          );
          setSelected(res.doc_id);
          // §23: a new document must refresh graph, indexes and coverage dashboards.
          void qc.invalidateQueries({ queryKey: ['coverage'] });
          void qc.invalidateQueries({ queryKey: ['graph'] });
          void qc.invalidateQueries({ queryKey: ['recent-articles'] });
        } catch (e) {
          setQueue((q) =>
            q.map((it) =>
              it.id === id
                ? { ...it, status: 'error', error: String(e instanceof Error ? e.message : e) }
                : it,
            ),
          );
        }
      }
    },
    [qc],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const fs = Array.from(e.dataTransfer.files || []);
    if (fs.length) void run(fs);
  };

  const selItem = queue.find((it) => it.result?.doc_id === selected);

  return (
    <div className="panel mt-5 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
        <UploadCloud size={15} className="text-copper" /> Очередь загрузки → хранилище
      </div>

      {/* Dropzone (multi-file) */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-4 py-6 text-center transition ${
          drag ? 'border-copper bg-copper/10' : 'border-line hover:border-copper/50'
        }`}
      >
        <UploadCloud size={22} className="text-faint" />
        <div className="text-sm text-nickel">Перетащите файлы или нажмите, чтобы выбрать</div>
        <div className="font-mono text-[10px] text-faint">PDF · DOCX · PPTX · XLSX · TXT · MD (до 64 МБ)</div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            const fs = Array.from(e.target.files || []);
            if (fs.length) void run(fs);
            e.target.value = '';
          }}
        />
      </div>

      {/* The queue: every doc + its real storage-landing confirmation */}
      {queue.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {queue.map((it) => (
            <QueueRow
              key={it.id}
              item={it}
              active={!!it.result && it.result.doc_id === selected}
              onSelect={() => it.result && setSelected(it.result.doc_id)}
            />
          ))}
        </div>
      )}

      {selItem?.result && <UploadResultView result={selItem.result} qc={qc} />}
    </div>
  );
}

let _qk = 0;
const queueKey = () => `${++_qk}`;

// One queue row = one document + its VERIFIED storage landing (graph counts + search index),
// polled from GET /documents/{id}/storage until it reports indexed.
function QueueRow({
  item,
  active,
  onSelect,
}: {
  item: QueueItem;
  active: boolean;
  onSelect: () => void;
}) {
  const docId = item.result?.doc_id;
  const done = item.status === 'done' || item.status === 'skipped';
  const storage = useQuery({
    queryKey: ['doc-storage', docId],
    queryFn: () => api.documentStorage(docId as string),
    enabled: !!docId && done,
    refetchInterval: (q) => (q.state.data?.indexed ? false : 3000),
    staleTime: 2000,
  });
  const s = storage.data;

  return (
    <div
      onClick={onSelect}
      className={`flex items-center gap-2 rounded border px-2.5 py-2 text-[12px] ${
        active ? 'border-copper/50 bg-copper/5' : 'border-line/60'
      } ${item.result ? 'cursor-pointer hover:border-copper/40' : ''}`}
    >
      {item.status === 'uploading' ? (
        <Loader2 size={13} className="shrink-0 animate-spin text-copper" />
      ) : item.status === 'error' ? (
        <X size={13} className="shrink-0 text-contradiction" />
      ) : (
        <Check size={13} className="shrink-0 text-verified" />
      )}
      <span className="truncate text-ink">{item.result?.title || item.name}</span>

      {item.status === 'uploading' && (
        <span className="ml-auto font-mono text-[10px] text-faint">парсинг + извлечение…</span>
      )}
      {item.status === 'error' && (
        <span className="ml-auto truncate text-[10px] text-contradiction">{item.error?.slice(0, 60)}</span>
      )}
      {done && (
        <span className="ml-auto flex flex-wrap items-center justify-end gap-1.5 font-mono text-[10px]">
          {item.status === 'skipped' && <span className="chip text-faint">уже в базе</span>}
          {s ? (
            <>
              <span
                className={`chip ${s.graph.in_graph ? 'border-verified/40 text-verified' : 'border-gap/40 text-gap'}`}
                title="узлы в графе Neo4j"
              >
                {s.graph.in_graph ? '✓ в графе' : 'нет в графе'} · {item.result?.node_count ?? 0} узл · {s.graph.chunks} чанк
              </span>
              <span
                className={`chip flex items-center gap-1 ${s.indexed ? 'border-verified/40 text-verified' : 'border-gap/40 text-gap'}`}
                title="членство в поисковом индексе Qdrant / OpenSearch"
              >
                <Database size={10} />
                {s.indexed ? 'в индексе' : 'не в индексе'}
                {s.qdrant != null ? ` · Q ${s.qdrant}` : ''}
                {s.opensearch != null ? ` · OS ${s.opensearch}` : ''}
              </span>
            </>
          ) : storage.isError ? (
            <span className="chip flex items-center gap-1 border-gap/40 text-gap">
              <CircleAlert size={10} /> нет подтверждения
            </span>
          ) : (
            <Loader2 size={11} className="animate-spin text-faint" />
          )}
        </span>
      )}
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
