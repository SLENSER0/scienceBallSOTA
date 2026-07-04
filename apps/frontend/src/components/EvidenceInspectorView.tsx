import { useEffect, useState } from 'react';
import {
  Braces,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleSlash,
  Cpu,
  FileText,
  GitBranch,
  Loader2,
  Search,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import { useStore } from '../store';

// §17.13 Evidence Inspector — полный provenance-бандл §5.2.6 поверх живого графа.
// Drawer уже подсвечивает span в исходном абзаце; этот экран добавляет НЕДОСТАЮЩИЕ
// поля доверия к каждому факту: parsed structured object (JSON-виджет), extractor/
// model version, reviewer decision (кто/когда/почему), ссылку на сгенерированное
// graph edge (клик → подсветка ребра в Graph Explorer) и prev/next по соседним
// доказательствам в рамках ребра/сущности. Reviewer decision сохраняется через
// POST /decision. Открывается по evidence id ИЛИ по edge id (source|TYPE|target),
// т.е. тот же инспектор доступен и из чата (citation), и из Graph Explorer (edge).

interface ExtractorInfo {
  run_id?: string | null;
  linked_via?: string | null;
  extractor?: string | null;
  model?: string | null;
  extractor_version?: string | null;
  pipeline_version?: string | null;
  prompt_version?: string | null;
  schema_version?: string | null;
  seed?: unknown;
  created_at?: string | null;
}

interface ReviewerDecision {
  review_status?: string | null;
  verified?: boolean | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_reason?: string | null;
}

interface LinkedEdge {
  edge_id: string;
  source: string;
  source_name?: string | null;
  target: string;
  target_name?: string | null;
  type: string;
  confidence?: number | null;
  relation: string;
}

interface Navigation {
  context: string;
  context_id?: string | null;
  index: number;
  total: number;
  prev_id?: string | null;
  next_id?: string | null;
  sibling_ids: string[];
}

interface ProvenanceBundle {
  evidence_id: string;
  found: boolean;
  statement?: string | null;
  doc_id?: string | null;
  doc_title?: string | null;
  page?: number | null;
  table_id?: string | null;
  figure_id?: string | null;
  paragraph_id?: string | null;
  source_type?: string | null;
  evidence_strength?: string | null;
  confidence?: number | null;
  practice_type?: string | null;
  country?: string | null;
  year?: number | null;
  span?: string | null;
  chunk_text?: string | null;
  highlight_offset: number;
  highlight_len: number;
  parsed_object: Record<string, unknown>;
  extractor: ExtractorInfo;
  reviewer: ReviewerDecision;
  linked_edges: LinkedEdge[];
  navigation?: Navigation | null;
}

interface EdgeEvidence {
  edge_id: string;
  source: string;
  target: string;
  type: string;
  found: boolean;
  evidence_ids: string[];
  count: number;
  first?: ProvenanceBundle | null;
}

const BASE = '/api/v1/evidence-inspector';

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

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

const PRACTICE: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};

// Static class strings (dynamic `text-${tone}` would be purged by Tailwind).
const DECISIONS: { id: string; label: string; cls: string }[] = [
  { id: 'accepted', label: 'Подтвердить', cls: 'text-verified hover:border-verified/50' },
  { id: 'corrected', label: 'Исправлено', cls: 'text-copper hover:border-copper/50' },
  { id: 'needs_review', label: 'На ревью', cls: 'text-gap hover:border-gap/50' },
  { id: 'rejected', label: 'Отклонить', cls: 'text-contradiction hover:border-contradiction/50' },
];

export function EvidenceInspectorView() {
  const setView = useStore((s) => s.setView);
  const setSelectedNode = useStore((s) => s.setSelectedNode);
  // Optional deep-link field (see wiring): populated when opened from chat citation
  // or a Graph Explorer edge click. Read defensively so no store edit is required.
  const initial = useStore(
    (s) => (s as unknown as { inspectEvidenceId?: string }).inspectEvidenceId,
  );

  const [input, setInput] = useState(initial ?? '');
  const [bundle, setBundle] = useState<ProvenanceBundle | null>(null);
  const [edgeCtx, setEdgeCtx] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const loadEvidence = async (id: string, edgeId?: string | null) => {
    if (!id.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const qs = edgeId ? `?edge_id=${encodeURIComponent(edgeId)}` : '';
      const b = await getJson<ProvenanceBundle>(
        `${BASE}/${encodeURIComponent(id.trim())}${qs}`,
      );
      setBundle(b);
      setEdgeCtx(edgeId ?? null);
      if (!b.found) setError(`Доказательство не найдено: ${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const loadEdge = async (edgeId: string) => {
    if (!edgeId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const ee = await getJson<EdgeEvidence>(
        `${BASE}/by-edge/${encodeURIComponent(edgeId.trim())}`,
      );
      if (!ee.found || !ee.first) {
        setBundle(null);
        setError(`У ребра нет доказательств: ${edgeId}`);
      } else {
        setBundle(ee.first);
        setEdgeCtx(edgeId.trim());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // Auto-load when opened with a pre-selected evidence id (from chat / graph).
  useEffect(() => {
    if (initial) void loadEvidence(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const submit = () => {
    const v = input.trim();
    if (!v) return;
    // Heuristic: an edge id is "source|TYPE|target".
    if (v.split('|').length === 3) void loadEdge(v);
    else void loadEvidence(v);
  };

  const decide = async (status: string) => {
    if (!bundle) return;
    setSaving(status);
    setError(null);
    // Optimistic update of the reviewer block.
    const prev = bundle.reviewer;
    setBundle({ ...bundle, reviewer: { ...prev, review_status: status } });
    try {
      const res = await fetch(
        `${BASE}/${encodeURIComponent(bundle.evidence_id)}/decision`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ status, reason: '' }),
        },
      );
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const r = (await res.json()) as ReviewerDecision & { review_status: string };
      setBundle((b) => (b ? { ...b, reviewer: { ...b.reviewer, ...r } } : b));
    } catch (e) {
      setBundle((b) => (b ? { ...b, reviewer: prev } : b)); // rollback
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  };

  const openEdgeInGraph = (edge: LinkedEdge) => {
    // Focus the edge's source entity in the graph explorer.
    setSelectedNode({ id: edge.source, label: edge.source_name ?? edge.source, type: 'Entity' });
    setView('largegraph');
  };

  const nav = bundle?.navigation;

  return (
    <div className="mx-auto max-w-4xl px-6 py-6">
      <div className="mb-1 flex items-center gap-2">
        <ShieldCheck size={18} className="text-copper" />
        <h1 className="text-lg font-semibold text-ink">Инспектор доказательства</h1>
      </div>
      <p className="mb-5 text-sm text-muted">
        Полная цепочка доверия к факту: извлечённое утверждение, источник и цитата в
        контексте, разобранные данные, кто и когда проверил, и связанная с фактом связь в
        графе. Введите идентификатор доказательства или связи вида{' '}
        <span className="font-mono text-nickel">источник|СВЯЗЬ|цель</span>.
      </p>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="идентификатор доказательства или источник|СВЯЗЬ|цель"
            className="w-full rounded-md border border-line bg-surface/60 py-2 pl-9 pr-3 text-sm text-ink outline-none focus:border-copper/50"
          />
        </div>
        <button
          onClick={submit}
          disabled={!input.trim() || loading}
          className="chip border-copper/40 text-copper hover:bg-copper/10 disabled:opacity-40"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : 'Открыть'}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
          {error}
        </div>
      )}

      {bundle?.found && (
        <div className="mt-6 space-y-5">
          {nav && nav.total > 1 && <NavBar nav={nav} edgeCtx={edgeCtx} onGo={loadEvidence} />}

          <SourceHeader b={bundle} />
          <StatementBlock b={bundle} />
          <ChunkBlock b={bundle} />
          <ParsedObjectBlock obj={bundle.parsed_object} />
          <ExtractorBlock x={bundle.extractor} />
          <ReviewerBlock r={bundle.reviewer} onDecide={decide} saving={saving} />
          <EdgesBlock edges={bundle.linked_edges} onOpen={openEdgeInGraph} onLoadEdge={loadEdge} />
        </div>
      )}
    </div>
  );
}

function NavBar({
  nav,
  edgeCtx,
  onGo,
}: {
  nav: Navigation;
  edgeCtx: string | null;
  onGo: (id: string, edgeId?: string | null) => void;
}) {
  const label =
    nav.context === 'edge' ? 'в рамках ребра' : nav.context === 'fact' ? 'в рамках факта' : '';
  return (
    <div className="flex items-center justify-between rounded-md border border-line bg-surface/40 px-3 py-2">
      <button
        onClick={() => nav.prev_id && onGo(nav.prev_id, edgeCtx)}
        disabled={!nav.prev_id}
        className="chip flex items-center gap-1 text-nickel disabled:opacity-30"
      >
        <ChevronLeft size={13} /> назад
      </button>
      <span className="font-mono text-[11px] text-faint">
        {nav.index + 1} / {nav.total} {label && <span className="text-muted">· {label}</span>}
      </span>
      <button
        onClick={() => nav.next_id && onGo(nav.next_id, edgeCtx)}
        disabled={!nav.next_id}
        className="chip flex items-center gap-1 text-nickel disabled:opacity-30"
      >
        вперёд <ChevronRight size={13} />
      </button>
    </div>
  );
}

function SourceHeader({ b }: { b: ProvenanceBundle }) {
  return (
    <div className="flex items-start gap-2">
      <FileText size={16} className="mt-0.5 shrink-0 text-copper" />
      <div className="min-w-0">
        <div className="truncate text-sm text-ink">{b.doc_title || b.doc_id || 'источник'}</div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {b.practice_type && (
            <span className="chip text-faint">{PRACTICE[b.practice_type] ?? b.practice_type}</span>
          )}
          {b.year && <span className="chip text-faint">{b.year}</span>}
          {b.page != null && <span className="chip text-faint">стр. {b.page}</span>}
          {b.table_id && <span className="chip text-faint">табл. {b.table_id}</span>}
          {b.figure_id && <span className="chip text-faint">рис. {b.figure_id}</span>}
          {b.paragraph_id && <span className="chip text-faint">абз. {b.paragraph_id}</span>}
          {b.source_type && <span className="chip text-faint">{b.source_type}</span>}
          {b.evidence_strength && <span className="chip text-faint">{b.evidence_strength}</span>}
          {typeof b.confidence === 'number' && (
            <span className="chip text-copper">conf {Math.round(b.confidence * 100)}%</span>
          )}
        </div>
        <div className="mt-1 font-mono text-[10px] text-faint">{b.evidence_id}</div>
      </div>
    </div>
  );
}

function StatementBlock({ b }: { b: ProvenanceBundle }) {
  if (!b.statement) return null;
  return (
    <div>
      <div className="eyebrow mb-1.5">извлечённое утверждение</div>
      <blockquote className="rounded border-l-2 border-copper bg-surface/60 px-3 py-2 text-sm italic text-ink/85">
        «{b.statement}»
      </blockquote>
    </div>
  );
}

function ChunkBlock({ b }: { b: ProvenanceBundle }) {
  if (!b.chunk_text) return null;
  const off = b.highlight_offset;
  const len = b.highlight_len;
  let content: React.ReactNode;
  if (off < 0 || len <= 0) {
    content = <mark className="rounded bg-copper/25 px-0.5 text-ink">{b.span}</mark>;
  } else {
    const start = Math.max(0, off - 400);
    const end = off + len + 400;
    const before = (start > 0 ? '…' : '') + b.chunk_text.slice(start, off);
    const hit = b.chunk_text.slice(off, off + len);
    const after = b.chunk_text.slice(off + len, end) + (b.chunk_text.length > end ? '…' : '');
    content = (
      <>
        {before}
        <mark className="rounded bg-copper/30 px-0.5 font-medium text-ink">{hit}</mark>
        {after}
      </>
    );
  }
  return (
    <div>
      <div className="eyebrow mb-1.5">цитата в контексте абзаца</div>
      <div className="rounded-md border border-line bg-surface/50 px-3 py-2.5 text-[13px] leading-relaxed text-ink/90">
        {content}
      </div>
    </div>
  );
}

function ParsedObjectBlock({ obj }: { obj: Record<string, unknown> }) {
  const keys = Object.keys(obj ?? {});
  return (
    <div>
      <div className="eyebrow mb-1.5 flex items-center gap-1.5">
        <Braces size={12} className="text-copper" /> разобранные данные факта
      </div>
      {keys.length === 0 ? (
        <div className="text-sm text-faint">Структурированных данных нет.</div>
      ) : (
        <pre className="max-h-72 overflow-auto rounded-md border border-line bg-surface/50 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-nickel">
          {JSON.stringify(obj, null, 2)}
        </pre>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value == null || value === '') return null;
  return (
    <div className="flex justify-between gap-3 border-b border-line/50 pb-1.5">
      <dt className="font-mono text-[11px] uppercase tracking-wide text-faint">{label}</dt>
      <dd className="text-right font-mono text-xs text-ink/90">{value}</dd>
    </div>
  );
}

function ExtractorBlock({ x }: { x: ExtractorInfo }) {
  const empty = !x.run_id && !x.extractor && !x.model;
  return (
    <div>
      <div className="eyebrow mb-1.5 flex items-center gap-1.5">
        <Cpu size={12} className="text-copper" /> как получен факт
      </div>
      {empty ? (
        <div className="text-sm text-faint">Источник обработки не указан.</div>
      ) : (
        <dl className="space-y-2 rounded-md border border-line bg-surface/40 px-3 py-2.5 text-sm">
          <Row label="extractor" value={x.extractor} />
          <Row label="model" value={x.model} />
          <Row label="extractor ver" value={x.extractor_version} />
          <Row label="pipeline ver" value={x.pipeline_version} />
          <Row label="prompt ver" value={x.prompt_version} />
          <Row label="schema ver" value={x.schema_version} />
          <Row label="seed" value={x.seed != null ? String(x.seed) : undefined} />
          <Row label="run id" value={x.run_id} />
          <Row
            label="связь"
            value={x.linked_via === 'edge' ? 'через связь графа' : x.linked_via ?? undefined}
          />
        </dl>
      )}
    </div>
  );
}

function ReviewerBlock({
  r,
  onDecide,
  saving,
}: {
  r: ReviewerDecision;
  onDecide: (status: string) => void;
  saving: string | null;
}) {
  const status = r.review_status;
  return (
    <div>
      <div className="eyebrow mb-1.5 flex items-center gap-1.5">
        <UserCheck size={12} className="text-copper" /> решение ревьюера
      </div>
      <div className="rounded-md border border-line bg-surface/40 px-3 py-2.5">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
          {status ? (
            <span
              className={`chip ${
                status === 'accepted' || status === 'corrected'
                  ? 'text-verified'
                  : status === 'rejected'
                    ? 'text-contradiction'
                    : 'text-gap'
              }`}
            >
              {status === 'accepted' || status === 'corrected' ? (
                <CircleCheck size={12} className="mr-1 inline" />
              ) : (
                <CircleSlash size={12} className="mr-1 inline" />
              )}
              {status}
            </span>
          ) : (
            <span className="chip text-faint">не проверено</span>
          )}
          {r.reviewed_by && <span className="text-xs text-muted">кто: {r.reviewed_by}</span>}
          {r.reviewed_at && (
            <span className="font-mono text-[10px] text-faint">{r.reviewed_at.slice(0, 19)}</span>
          )}
        </div>
        {r.review_reason && (
          <div className="mb-2 text-xs text-muted">комментарий: {r.review_reason}</div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {DECISIONS.map((d) => (
            <button
              key={d.id}
              onClick={() => onDecide(d.id)}
              disabled={saving != null}
              className={`chip border-line ${d.cls} disabled:opacity-40`}
            >
              {saving === d.id ? <Loader2 size={12} className="animate-spin" /> : d.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function EdgesBlock({
  edges,
  onOpen,
  onLoadEdge,
}: {
  edges: LinkedEdge[];
  onOpen: (e: LinkedEdge) => void;
  onLoadEdge: (edgeId: string) => void;
}) {
  return (
    <div>
      <div className="eyebrow mb-1.5 flex items-center gap-1.5">
        <GitBranch size={12} className="text-copper" /> связи факта в графе
      </div>
      {edges.length === 0 ? (
        <div className="text-sm text-faint">Связанных рёбер не найдено.</div>
      ) : (
        <div className="space-y-1.5">
          {edges.map((e) => (
            <div
              key={e.edge_id}
              className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface/40 px-3 py-2 text-sm"
            >
              <div className="min-w-0">
                <div className="truncate text-ink/90">
                  <span className="text-nickel">{e.source_name ?? e.source}</span>{' '}
                  <span className="font-mono text-[11px] text-copper">—[{e.type}]→</span>{' '}
                  <span className="text-nickel">{e.target_name ?? e.target}</span>
                </div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="chip text-faint">
                    {e.relation === 'supported_by' ? 'обосновывает факт' : 'выведено из доказ.'}
                  </span>
                  {typeof e.confidence === 'number' && (
                    <span className="chip text-copper">conf {Math.round(e.confidence * 100)}%</span>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <button
                  onClick={() => onLoadEdge(e.edge_id)}
                  title="Доказательства этого ребра"
                  className="chip text-nickel hover:text-copper"
                >
                  доказ.
                </button>
                <button
                  onClick={() => onOpen(e)}
                  title="Подсветить в Graph Explorer"
                  className="chip border-copper/40 text-copper hover:bg-copper/10"
                >
                  в графе
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
