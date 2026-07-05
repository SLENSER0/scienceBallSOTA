import { useId, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useMutation } from '@tanstack/react-query';
import { useStore } from '../store';
import {
  Brain,
  Check,
  ChevronDown,
  ChevronUp,
  DatabaseZap,
  ExternalLink,
  Loader2,
  Pencil,
  RotateCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  X,
} from 'lucide-react';
import { api, type DeepResearchSource, type GapAnalysisResult, type TrustedSource } from '../api';
import type { PrioritizedGap } from '../types';

// Gaps the user has «closed» (research ran + ≥1 source ingested into the graph) are hidden from
// the map and STAY hidden across a reload / re-scan — persisted client-side so «мы решили этот
// пробел» sticks even though the backend gap-scanner would otherwise resurface it.
const SOLVED_KEY = 'sb.solvedGaps';
export function getSolvedGaps(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SOLVED_KEY) || '[]') as string[]);
  } catch {
    return new Set();
  }
}
export function markGapSolved(id: string): void {
  try {
    const s = getSolvedGaps();
    s.add(id);
    localStorage.setItem(SOLVED_KEY, JSON.stringify([...s]));
  } catch {
    /* localStorage unavailable — in-session removal via closeGap still works */
  }
}

const DOMAIN_RU_FULL: Record<string, string> = {
  hydrometallurgy: 'гидрометаллургия',
  pyrometallurgy: 'пирометаллургия',
  environment: 'экология и охрана окружающей среды',
  waste_processing: 'переработка отходов',
  water_treatment: 'водоочистка',
  mineral_processing: 'обогащение полезных ископаемых',
  electrometallurgy: 'электрометаллургия',
};

const TAX5_ANGLE: Record<string, string> = {
  TRUE_GAP:
    'В корпусе по этой теме данных нет — найди первичные исследования, промышленные практики и числовые режимы.',
  CONTRADICTED:
    'Источники в корпусе расходятся — найди независимые данные, разрешающие противоречие, с условиями измерений.',
  WEAK_EVIDENCE:
    'Доказательная база тонкая — найди дополнительные подтверждающие исследования с воспроизводимыми числами.',
  POSSIBLE_EXTRACTION_GAP:
    'Факт, вероятно, есть в литературе, но не извлечён — найди конкретные источники, где он приведён.',
  KNOWN: 'Уточни и расширь известные данные свежими источниками.',
};

export function composeQuestion(g: PrioritizedGap): string {
  const focus = (g.name ?? '').trim().replace(/\s+/g, ' ');
  const domain = g.domain ? DOMAIN_RU_FULL[g.domain] ?? g.domain : '';
  const angle = g.taxonomy5 ? TAX5_ANGLE[g.taxonomy5] : '';
  const parts: string[] = [
    `Исследовательский запрос для горно-металлургического R&D (контекст Норникеля): ${
      focus || 'пробел в знаниях'
    }.`,
  ];
  if (domain) parts.push(`Область: ${domain}.`);
  if (g.rationale?.trim()) parts.push(`Почему важно: ${g.rationale.trim()}`);
  if (g.action?.trim()) parts.push(`Что нужно выяснить: ${g.action.trim()}`);
  if (angle) parts.push(angle);
  parts.push(
    'Нужны конкретные методы и технологии, числовые условия и параметры с единицами измерения, ' +
      'сравнение отечественных и зарубежных практик, ссылки на источники.',
  );
  return parts.join(' ');
}

type PromoteResult = { ingested: TrustedSource[]; review: TrustedSource[] };

const TRUST_CHIP: Record<string, string> = {
  high: 'border-verified/40 text-verified',
  medium: 'border-copper/40 text-copper',
  low: 'border-gap/40 text-gap',
  untrusted: 'border-contradiction/40 text-contradiction',
};
const trustChip = (tier: string) => TRUST_CHIP[tier] ?? 'border-line text-faint';

const FRESH_CHIP: Record<string, string> = {
  fresh: 'border-verified/40 text-verified',
  aging: 'border-copper/40 text-copper',
  stale: 'border-contradiction/40 text-contradiction',
  unknown: 'border-line text-faint',
};
const FRESH_LABEL: Record<string, string> = {
  fresh: 'свежий',
  aging: 'устаревает',
  stale: 'устарел',
  unknown: 'дата неизв.',
};
const freshChip = (f: string) => FRESH_CHIP[f] ?? 'border-line text-faint';
const freshLabel = (f: string) => FRESH_LABEL[f] ?? f;

const hostOf = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

type ProgStatus = 'pending' | 'loading' | 'ingested' | 'review' | 'error';
type ProgItem = { title: string; status: ProgStatus; item?: TrustedSource };
const PROG_LABEL: Record<ProgStatus, string> = {
  pending: 'в очереди',
  loading: 'загружается…',
  ingested: 'в графе',
  review: 'на ревью',
  error: 'ошибка',
};
function ProgIcon({ status }: { status: ProgStatus }) {
  if (status === 'loading') return <Loader2 size={12} className="shrink-0 animate-spin text-copper" />;
  if (status === 'ingested') return <Check size={12} className="shrink-0 text-verified" />;
  if (status === 'error') return <X size={12} className="shrink-0 text-contradiction" />;
  if (status === 'review') return <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-gap" />;
  return <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-line" />;
}

const ANALYZE_TIMEOUT_MS = 60_000;
const RUN_TIMEOUT_MS = 120_000;
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout: истекло время ожидания')), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      },
    );
  });
}

// Compact 3-phase progress: анализ → поиск → отчёт. Makes the deep-research pipeline
// legible at a glance in the demo.
type StageState = 'idle' | 'active' | 'done';
function StageDot({ label, state }: { label: string; state: StageState }) {
  const color =
    state === 'done' ? 'text-verified' : state === 'active' ? 'text-copper' : 'text-faint';
  return (
    <div className="flex items-center gap-1.5">
      {state === 'active' ? (
        <Loader2 size={12} className="animate-spin text-copper" aria-hidden />
      ) : state === 'done' ? (
        <Check size={12} className="text-verified" aria-hidden />
      ) : (
        <span className="h-2.5 w-2.5 rounded-full border border-line" />
      )}
      <span className={`font-mono text-[10px] uppercase tracking-wide ${color}`}>{label}</span>
    </div>
  );
}

export function GapDeepResearchPanel({ g }: { g: PrioritizedGap }) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [hasRun, setHasRun] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [question, setQuestion] = useState(() => composeQuestion(g));

  const [analysis, setAnalysis] = useState<GapAnalysisResult | null>(null);
  const [report, setReport] = useState('');
  const [sources, setSources] = useState<DeepResearchSource[]>([]);
  const [promote, setPromote] = useState<PromoteResult | null>(null);

  // «Закрыть пробел»: once the load finished and ≥1 source actually landed in the graph, the
  // gap is solved → confirm, then drop the card from the map. Crucially this fires only AFTER
  // the load loop completes (see onSolved in LoadToGraphPanel), never on the first incremental
  // ingest — the earlier mid-load removal unmounted this panel, aborting the loop.
  const closeGap = useStore((s) => s.closeGap);
  const ingestedCount = promote?.ingested.length ?? 0;
  const [solved, setSolved] = useState(false);
  const solvedRef = useRef(false);
  const markSolved = () => {
    if (solvedRef.current) return;
    solvedRef.current = true;
    setSolved(true);
    markGapSolved(g.id); // persist so a reload / re-scan keeps it hidden
    setTimeout(() => closeGap(g.id), 1600); // let the «закрыт» confirmation show first
  };

  const run = useMutation({
    mutationFn: (a: GapAnalysisResult) => withTimeout(api.runResearch(a.question, a.queries), RUN_TIMEOUT_MS),
    onSuccess: (r) => {
      setReport(r.report);
      setSources(r.sources);
      setPromote(null);
    },
  });
  const analyze = useMutation({
    mutationFn: (q: string) => withTimeout(api.analyzeGaps(q, null), ANALYZE_TIMEOUT_MS),
    onMutate: () => {
      setAnalysis(null);
      setReport('');
      setSources([]);
      setPromote(null);
    },
    onSuccess: (a) => {
      setAnalysis(a);
      run.mutate(a);
    },
  });

  const pending = analyze.isPending || run.isPending;
  const analyzeFailed = analyze.isError && !analyze.isPending;
  const runFailed = run.isError && !run.isPending;

  // Stage states for the 3-phase progress row.
  const stage1: StageState = analyze.isPending
    ? 'active'
    : analyzeFailed
      ? 'idle'
      : analysis || run.isPending || report
        ? 'done'
        : 'idle';
  const stage2: StageState = run.isPending ? 'active' : report ? 'done' : 'idle';
  const stage3: StageState = report ? 'done' : 'idle';

  const start = () => {
    if (pending || !question.trim()) return;
    setHasRun(true);
    analyze.mutate(question);
  };
  const onToggle = () => {
    const willOpen = !open;
    setOpen(willOpen);
    if (willOpen && !hasRun) start();
  };

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex items-center gap-1.5 rounded-md bg-copper/20 px-4 py-1.5 text-sm text-copper transition enabled:hover:bg-copper/30 disabled:opacity-40"
      >
        {pending && !open ? (
          <Loader2 size={14} className="animate-spin" aria-hidden />
        ) : (
          <Brain size={14} aria-hidden />
        )}
        Закрыть пробел через дип рисёрч
        {open ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}
      </button>

      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={`Дип рисёрч по пробелу: ${g.name}`}
          aria-busy={pending}
          className="mt-3 rounded-md border border-copper/30 bg-surface/40 p-3"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-xs text-nickel">
              <Sparkles size={14} className="text-copper" aria-hidden /> Дип рисёрч по пробелу
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setShowEdit((v) => !v)}
                aria-pressed={showEdit}
                aria-controls={`${panelId}-q`}
                className="chip flex items-center gap-1.5 border-line text-faint hover:text-ink disabled:opacity-40"
                title="Показать и изменить исследовательский запрос"
              >
                <Pencil size={11} aria-hidden /> запрос
              </button>
              {(report || sources.length > 0 || analyzeFailed || runFailed) && !pending && (
                <button
                  type="button"
                  onClick={start}
                  disabled={pending || !question.trim()}
                  className="chip flex items-center gap-1.5 border-line text-faint hover:text-ink disabled:opacity-40"
                  title="Запустить дип рисёрч заново"
                >
                  <RotateCw size={11} aria-hidden /> заново
                </button>
              )}
            </div>
          </div>

          {ingestedCount > 0 && (
            <div className="mb-2 flex items-center gap-1.5 rounded bg-verified/10 px-2.5 py-1.5 text-[12px] text-verified">
              <Check size={13} aria-hidden /> Пробел закрыт — {ingestedCount} источн. добавлено в
              граф.{solved ? ' Убираю карточку из карты…' : ''}
            </div>
          )}

          {/* 3-phase progress: анализ → поиск → отчёт */}
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            <StageDot label="анализ" state={stage1} />
            <span className="text-faint" aria-hidden>
              ›
            </span>
            <StageDot label="поиск" state={stage2} />
            <span className="text-faint" aria-hidden>
              ›
            </span>
            <StageDot label="отчёт" state={stage3} />
          </div>

          {showEdit && (
            <div className="mb-3">
              <label
                htmlFor={`${panelId}-q`}
                className="mb-1 block text-[10px] uppercase tracking-wide text-faint"
              >
                исследовательский запрос
              </label>
              <textarea
                id={`${panelId}-q`}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
                className="w-full resize-none rounded-md border border-line bg-surface/60 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
              />
              <button
                type="button"
                onClick={start}
                disabled={pending || !question.trim()}
                className="mt-2 flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-4 py-1.5 text-sm text-copper transition enabled:hover:bg-copper/20 disabled:opacity-40"
              >
                {pending ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <RotateCw size={14} aria-hidden />}
                Запустить с этим запросом
              </button>
            </div>
          )}

          <div aria-live="polite" className="min-h-[1rem]">
            {analyze.isPending && (
              <div className="flex items-center gap-1.5 font-mono text-[11px] text-faint">
                <Loader2 size={12} className="animate-spin" aria-hidden /> Анализирую пробел…
              </div>
            )}
            {run.isPending && (
              <div className="flex items-center gap-1.5 font-mono text-[11px] text-faint">
                <Loader2 size={12} className="animate-spin" aria-hidden /> Ищу источники и собираю отчёт…
              </div>
            )}
          </div>

          {analyzeFailed && (
            <div className="mt-1 flex items-center gap-2 text-[11px] text-contradiction">
              <span>Анализ пробела не удался.</span>
              <button
                type="button"
                onClick={start}
                className="chip flex items-center gap-1.5 border-line text-faint hover:text-ink"
              >
                <RotateCw size={11} aria-hidden /> повторить
              </button>
            </div>
          )}
          {!analyzeFailed && runFailed && (
            <div className="mt-1 flex items-center gap-2 text-[11px] text-contradiction">
              <span>Поиск источников не удался.</span>
              <button
                type="button"
                onClick={() => analysis && run.mutate(analysis)}
                className="chip flex items-center gap-1.5 border-line text-faint hover:text-ink"
              >
                <RotateCw size={11} aria-hidden /> повторить поиск
              </button>
            </div>
          )}

          {analysis && !analyze.isPending && (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-2 font-mono text-[10px] text-faint">
                <span className="chip">в корпусе · решений {analysis.have.n_solutions}</span>
                <span className="chip">фактов {analysis.have.n_facts}</span>
                <span className="chip">статей {analysis.have.n_papers}</span>
                <span className="chip border-gap/40 text-gap">пробелов {analysis.have.n_gaps}</span>
              </div>
              {analysis.missing.length > 0 && (
                <GapList title="Чего не хватает" items={analysis.missing} tone="gap" />
              )}
              {analysis.attention.length > 0 && (
                <GapList title="На что обратить внимание" items={analysis.attention} tone="copper" />
              )}
              {analysis.queries.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-faint">поисковые запросы</div>
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.queries.map((q, i) => (
                      <span key={i} className="chip border-line/60 text-[11px] text-muted">
                        {q}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {report && (
            <>
              <div className="mt-3 text-[10px] uppercase tracking-wide text-faint">Отчёт</div>
              <div className="md mt-1 max-h-[440px] overflow-y-auto rounded border border-line bg-graphite/30 p-3">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
              </div>
            </>
          )}

          {!run.isPending && sources.length > 0 && (
            <LoadToGraphPanel
              sources={sources}
              promote={promote}
              setPromote={setPromote}
              onSolved={markSolved}
            />
          )}
          {!run.isPending && report && sources.length === 0 && (
            <div className="mt-2 font-mono text-[11px] text-faint">
              Источников для загрузки в граф не найдено.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GapList({ title, items, tone }: { title: string; items: string[]; tone: 'gap' | 'copper' }) {
  const color = tone === 'gap' ? 'text-gap' : 'text-copper';
  return (
    <div>
      <div className={`mb-1 text-[10px] uppercase tracking-wide ${color}`}>{title}</div>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 rounded border border-line/60 px-2.5 py-1.5 text-[12px] text-muted">
            <span className={`mt-1.5 h-1 w-1 shrink-0 rounded-full ${tone === 'gap' ? 'bg-gap' : 'bg-copper'}`} />
            <span className="text-ink">{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LoadToGraphPanel({
  sources,
  promote,
  setPromote,
  onSolved,
}: {
  sources: DeepResearchSource[];
  promote: PromoteResult | null;
  setPromote: React.Dispatch<React.SetStateAction<PromoteResult | null>>;
  onSolved: () => void;
}) {
  const [progress, setProgress] = useState<ProgItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const withBusy = (id: string, on: boolean) =>
    setBusy((b) => {
      const n = new Set(b);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });

  const hasResult = !!promote && (promote.ingested.length > 0 || promote.review.length > 0);
  const attempted = !loading && progress.length > 0;
  const doneCount = progress.filter((p) => p.status !== 'pending' && p.status !== 'loading').length;

  const runLoad = async () => {
    if (!sources.length || loading) return;
    setLoading(true);
    setProgress(sources.map((s) => ({ title: s.title, status: 'pending' as ProgStatus })));
    const ingested: TrustedSource[] = [];
    const review: TrustedSource[] = [];
    for (let i = 0; i < sources.length; i++) {
      const s = sources[i];
      setProgress((p) => p.map((it, j) => (j === i ? { ...it, status: 'loading' } : it)));
      try {
        const r = await api.promoteDeepSources([
          { title: s.title, url: s.url, snippet: s.snippet, year: s.year ?? null },
        ]);
        const toReview = r.review.length > 0;
        const got = (toReview ? r.review[0] : r.ingested[0]) as TrustedSource | undefined;
        if (got) (toReview ? review : ingested).push(got);
        setProgress((p) =>
          p.map((it, j) => (j === i ? { ...it, status: toReview ? 'review' : 'ingested', item: got } : it)),
        );
        setPromote({ ingested: [...ingested], review: [...review] });
      } catch {
        setProgress((p) => p.map((it, j) => (j === i ? { ...it, status: 'error' } : it)));
      }
    }
    setLoading(false);
    // Gap solved once ≥1 source is actually in the graph — fires HERE, after the whole loop,
    // so removing the card can never abort an in-flight ingest.
    if (ingested.length > 0) onSolved();
  };

  const decide = (id: string, keep: boolean) =>
    setPromote((cur) => {
      if (!cur) return cur;
      const moved = cur.review.find((x) => x.id === id);
      return {
        ingested: keep && moved ? [...cur.ingested, moved] : cur.ingested,
        review: cur.review.filter((x) => x.id !== id),
      };
    });
  const approve = useMutation({
    mutationFn: (id: string) => api.approveSource(id),
    onMutate: (id) => withBusy(id, true),
    onSettled: (_r, _e, id) => withBusy(id, false),
    onSuccess: (_r, id) => {
      // Approving a review source puts it in the graph too → the gap counts as solved.
      decide(id, true);
      onSolved();
    },
  });
  const reject = useMutation({
    mutationFn: (id: string) => api.rejectSource(id),
    onMutate: (id) => withBusy(id, true),
    onSettled: (_r, _e, id) => withBusy(id, false),
    onSuccess: (_r, id) => decide(id, false),
  });

  return (
    <div className="mt-3 rounded border border-copper/30 bg-surface/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs text-nickel">
          <ShieldCheck size={14} className="text-copper" aria-hidden /> Доверие к источникам · найдено{' '}
          {sources.length}
        </div>
        {loading ? (
          <span
            aria-live="polite"
            className="flex items-center gap-1.5 rounded bg-copper/15 px-2.5 py-1 text-xs text-copper opacity-80"
          >
            <Loader2 size={13} className="animate-spin" aria-hidden />
            Загрузка {doneCount}/{sources.length}…
          </span>
        ) : hasResult ? (
          <span className="flex items-center gap-1 text-[11px] text-verified">
            <Check size={13} aria-hidden /> загружено
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void runLoad()}
            className="flex items-center gap-1.5 rounded bg-copper/15 px-2.5 py-1 text-xs text-copper hover:bg-copper/25"
          >
            <DatabaseZap size={13} aria-hidden />
            {attempted ? 'Повторить' : 'Загрузить в граф'}
          </button>
        )}
      </div>

      {loading && progress.length > 0 && (
        <div className="mb-3">
          <div className="mb-1.5 h-1 overflow-hidden rounded bg-line/40">
            <div
              className="h-full bg-copper transition-all"
              style={{ width: `${Math.round((doneCount / progress.length) * 100)}%` }}
            />
          </div>
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {progress.map((p, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded border border-line/50 px-2.5 py-1.5 text-[12px]"
              >
                <ProgIcon status={p.status} />
                <span className="truncate text-ink">{p.title}</span>
                {p.item && (
                  <span className={`chip ${trustChip(p.item.trust.trust_tier)}`}>
                    {p.item.trust.trust_tier} {p.item.trust.trust_score.toFixed(2)}
                  </span>
                )}
                <span
                  className={`ml-auto shrink-0 font-mono text-[10px] ${
                    p.status === 'review'
                      ? 'text-gap'
                      : p.status === 'error'
                        ? 'text-contradiction'
                        : 'text-faint'
                  }`}
                >
                  {PROG_LABEL[p.status]}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && promote && (
        <div className="space-y-3">
          {promote.ingested.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-faint">
                в графе ({promote.ingested.length})
              </div>
              <div className="space-y-1">
                {promote.ingested.map((r, i) => {
                  const safeUrl = /^https?:\/\//i.test((r.url ?? '').trim()) ? r.url : '';
                  return (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded border border-line/60 px-2.5 py-1.5 text-[12px]"
                    >
                      <Check size={12} className="shrink-0 text-verified" aria-hidden />
                      {safeUrl ? (
                        <a
                          href={safeUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex min-w-0 items-center gap-1 text-ink hover:text-copper"
                          title={safeUrl}
                        >
                          <span className="truncate">{r.title}</span>
                          <ExternalLink size={11} className="shrink-0 opacity-60" aria-hidden />
                        </a>
                      ) : (
                        <span className="truncate text-ink">{r.title}</span>
                      )}
                      <span className={`chip ${trustChip(r.trust.trust_tier)}`}>
                        {r.trust.trust_tier} {r.trust.trust_score.toFixed(2)}
                      </span>
                      <span className={`ml-auto chip ${freshChip(r.trust.freshness)}`}>
                        {freshLabel(r.trust.freshness)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {promote.review.length > 0 && (
            <div>
              <div className="mb-1.5 text-[10px] uppercase tracking-wide text-gap">
                на ревью — решите по каждому источнику ({promote.review.length})
              </div>
              <div className="space-y-2">
                {promote.review.map((r) => {
                  const warnings = r.trust.warnings ?? [];
                  const safeUrl = /^https?:\/\//i.test((r.url ?? '').trim()) ? r.url : '';
                  const isBusy = busy.has(r.id ?? '');
                  return (
                    <div key={r.id} className="rounded border border-gap/30 bg-graphite/20 px-2.5 py-2 text-[12px]">
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          {safeUrl ? (
                            <a
                              href={safeUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 font-medium text-ink hover:text-copper"
                              title={safeUrl}
                            >
                              <span className="truncate">{r.title}</span>
                              <ExternalLink size={11} className="shrink-0 opacity-60" aria-hidden />
                            </a>
                          ) : (
                            <span className="truncate font-medium text-ink">{r.title}</span>
                          )}
                          {safeUrl && (
                            <div className="mt-0.5 truncate font-mono text-[10px] text-faint">{hostOf(safeUrl)}</div>
                          )}
                        </div>
                        <span className="flex shrink-0 items-center gap-1">
                          <button
                            type="button"
                            onClick={() => r.id && approve.mutate(r.id)}
                            disabled={isBusy}
                            className="flex items-center gap-1 rounded bg-verified/15 px-2 py-1 text-[11px] text-verified hover:bg-verified/25 disabled:opacity-50"
                            title="Добавить источник в корпус"
                          >
                            <Check size={12} aria-hidden /> Добавить
                          </button>
                          <button
                            type="button"
                            onClick={() => r.id && reject.mutate(r.id)}
                            disabled={isBusy}
                            className="flex items-center gap-1 rounded bg-contradiction/15 px-2 py-1 text-[11px] text-contradiction hover:bg-contradiction/25 disabled:opacity-50"
                            title="Не добавлять"
                          >
                            <X size={12} aria-hidden /> Пропустить
                          </button>
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className={`chip ${trustChip(r.trust.trust_tier)}`}>
                          доверие: {r.trust.trust_tier} {r.trust.trust_score.toFixed(2)}
                        </span>
                        <span className={`chip ${freshChip(r.trust.freshness)}`}>{freshLabel(r.trust.freshness)}</span>
                        {r.year != null && <span className="chip border-line/60 text-faint">{r.year}</span>}
                      </div>
                      {warnings.length > 0 && (
                        <ul className="mt-1.5 space-y-0.5">
                          {warnings.map((w, i) => (
                            <li key={i} className="flex gap-1.5 text-[11px] text-gap">
                              <TriangleAlert size={11} className="mt-0.5 shrink-0" aria-hidden />
                              <span>{w}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
