import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookPlus,
  Brain,
  Check,
  DatabaseZap,
  ExternalLink,
  FlaskConical,
  ImagePlus,
  Library,
  Loader2,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  X,
} from 'lucide-react';
import { api, type TrustedSource } from '../api';
import { useStore } from '../store';
import { DocumentUpload } from './DocumentUpload';
import { MultimodalPanel } from './MultimodalPanel';
import { TabHub } from './TabHub';
import { SourcesShowcaseView } from './SourcesShowcaseView';

// «Библиотека» — add scientific articles to the graph. Two flows:
// (1) gap-informed research: analyze the prompt (+ optional image) against the corpus,
//     find gaps, web-search to close them, then review + ingest the found sources;
// (2) manual add: a form that writes a :Paper (+ abstract chunk/evidence) to the graph.

// Top-level «Библиотека» hub: sources showcase first, then the search/add flow.
export function LibraryView() {
  return (
    <TabHub
      eyebrow="библиотека · источники и добавление"
      tabs={[
        {
          id: 'sources',
          label: 'Источники корпуса',
          icon: Library,
          render: () => <SourcesShowcaseView />,
        },
        {
          id: 'add',
          label: 'Поиск и добавление статей',
          icon: Sparkles,
          render: () => <LibrarySearchTab />,
        },
      ]}
    />
  );
}

function LibrarySearchTab() {
  const qc = useQueryClient();
  const sources = useQuery({ queryKey: ['research-sources'], queryFn: api.researchSources });
  const recent = useQuery({ queryKey: ['recent-articles'], queryFn: api.recentArticles });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">Библиотека · добавление статей</div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Найти и добавить научные статьи
        </h1>
        <p className="mt-1 text-sm text-faint">
          Дип рисёрч анализирует ваш промпт и текущие данные корпуса, находит пробелы, ищет
          источники в вебе и даёт отчёт — каждую статью можно проверить на доверие и добавить в базу.
        </p>

        {/* Gap-informed (optionally multimodal) research */}
        <GapResearchPanel />

        {/* Upload document → graph + viewer (§17.19) */}
        <DocumentUpload />

        {/* Multimodal analysis — figures/micrographs/flowsheets (minimax-m3) */}
        <MultimodalPanel />

        {/* Two columns: manual add + recent */}
        {/* minmax(0,…) + min-w-0: без него неразрывный длинный заголовок/URL распирает колонку
            грида и ширина блоков «плавает». Заголовок обрезаем в одну строку с многоточием. */}
        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <ManualAddForm onAdded={() => void qc.invalidateQueries({ queryKey: ['recent-articles'] })} />
          <div className="panel min-w-0 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
              <FlaskConical size={15} className="text-copper" /> Недавно добавленные
            </div>
            {recent.data?.articles.length ? (
              <ul className="space-y-2">
                {recent.data.articles.map((a) => (
                  <li key={a.id} className="min-w-0 text-sm">
                    <div className="truncate text-ink" title={a.title}>
                      {a.title}
                    </div>
                    <div className="truncate font-mono text-[10px] text-faint">
                      {a.year ?? ''} {a.doi ? `· ${a.doi}` : ''}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="py-6 text-center font-mono text-[11px] text-faint">
                пока нет добавленных вручную статей
              </div>
            )}
            <div className="mt-3 border-t border-line pt-3 text-[11px] text-faint">
              Каталог источников: {sources.data?.sources.length ?? 0} баз (открытые, платные, теневая).
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Gap-informed research: промпт (+ картинка) → анализ пробелов → веб-поиск → отчёт + статьи.
function GapResearchPanel() {
  const deep = useStore((s) => s.deep);
  const setDeep = useStore((s) => s.setDeep);
  const [question, setQuestion] = useState('');
  const [image, setImage] = useState<string | null>(null);
  const a = deep.analysis;

  const analyze = useMutation({
    mutationFn: () => api.analyzeGaps(question, image),
    onSuccess: (r) => setDeep({ analysis: r, report: '', sources: [], promote: null }),
  });
  const run = useMutation({
    mutationFn: () => api.runResearch(a!.question, a!.queries),
    // Reset promote too: a fresh source batch must re-enable «Загрузить в граф» (else the
    // stale promote from the previous batch keeps the button hidden and the new sources
    // are stuck showing «загружено» forever).
    onSuccess: (r) => setDeep({ report: r.report, sources: r.sources, promote: null }),
  });

  const onImage = (f: File | null) => {
    if (!f) return setImage(null);
    const reader = new FileReader();
    reader.onload = () => setImage(String(reader.result));
    reader.readAsDataURL(f);
  };

  return (
    <div className="panel mt-5 border-copper/30 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
        <Sparkles size={15} className="text-copper" /> Дип рисёрч с анализом пробелов
      </div>
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Что нужно исследовать? Напр.: способы закачки шахтных вод в глубокие горизонты и требования к изоляции"
        rows={2}
        className="w-full resize-none rounded-md border border-line bg-surface/60 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
      />
      <div className="mt-2 flex items-center gap-2">
        <label className="flex cursor-pointer items-center gap-1.5 rounded border border-line px-2.5 py-1.5 text-xs text-faint hover:text-nickel">
          <ImagePlus size={13} /> {image ? 'картинка ✓' : 'картинка (опц.)'}
          <input type="file" accept="image/*" className="hidden" onChange={(e) => onImage(e.target.files?.[0] ?? null)} />
        </label>
        {image && <img src={image} alt="" className="h-10 rounded border border-line" />}
        <button
          onClick={() => question.trim() && analyze.mutate()}
          disabled={analyze.isPending || !question.trim()}
          className="ml-auto flex items-center gap-1.5 rounded-md bg-copper/20 px-4 py-1.5 text-sm text-copper transition enabled:hover:bg-copper/30 disabled:opacity-40"
        >
          {analyze.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          Анализ пробелов
        </button>
      </div>
      {analyze.isError && <div className="mt-1 text-[11px] text-contradiction">анализ не удался</div>}

      {a && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2 font-mono text-[10px] text-faint">
            <span className="chip">в корпусе · решений {a.have.n_solutions}</span>
            <span className="chip">фактов {a.have.n_facts}</span>
            <span className="chip">статей {a.have.n_papers}</span>
            <span className="chip border-gap/40 text-gap">пробелов {a.have.n_gaps}</span>
          </div>
          {a.vision && (
            <div className="rounded border border-line/60 bg-graphite/30 px-3 py-2 text-[12px] text-muted">
              <span className="text-faint">из изображения:</span> {a.vision}
            </div>
          )}
          {a.missing.length > 0 && (
            <GapList title="Чего не хватает" items={a.missing} tone="gap" />
          )}
          {a.attention.length > 0 && (
            <GapList title="На что обратить внимание" items={a.attention} tone="copper" />
          )}
          {a.queries.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-faint">поисковые запросы</div>
              <div className="flex flex-wrap gap-1.5">
                {a.queries.map((q, i) => (
                  <span key={i} className="chip border-line/60 text-[11px] text-muted">{q}</span>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-4 py-1.5 text-sm text-copper transition enabled:hover:bg-copper/20 disabled:opacity-40"
          >
            {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Brain size={14} />}
            Начать дип рисёрч
          </button>
        </div>
      )}

      {deep.report && (
        <div className="md mt-3 max-h-[440px] overflow-y-auto rounded border border-line bg-graphite/30 p-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{deep.report}</ReactMarkdown>
        </div>
      )}
      {run.isPending && !deep.report && (
        <div className="mt-2 font-mono text-[11px] text-faint">Ищу источники и собираю отчёт…</div>
      )}
      {!run.isPending && deep.sources.length > 0 && <LoadToGraphPanel />}
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

type PromoteResult = { ingested: TrustedSource[]; review: TrustedSource[] };

const TRUST_CHIP: Record<string, string> = {
  high: 'border-verified/40 text-verified',
  medium: 'border-copper/40 text-copper',
  low: 'border-gap/40 text-gap',
  untrusted: 'border-contradiction/40 text-contradiction',
};
const trustChip = (tier: string) => TRUST_CHIP[tier] ?? 'border-line text-faint';

// Domain shown under a review source's title — the host is the fastest trust cue.
const hostOf = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

// Freshness is a first-class review signal for web sources — recency shifts trust.
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

// «Загрузить в граф»: run each found source through Source Trust ONE AT A TIME so the loading
// is visible (sources don't ingest instantly): pending → loading → в графе / на ревью. Trusted
// ones go to the graph; low-trust ones are held for the user's add/reject decision (§23.27).
function LoadToGraphPanel() {
  const deep = useStore((s) => s.deep);
  const setDeep = useStore((s) => s.setDeep);
  const promote = deep.promote as PromoteResult | null;
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
  // A load counts as done only once it produced results — an all-error run stays retriable
  // instead of falsely reading as «загружено», and a successful one hides the button for good.
  const hasResult = !!promote && (promote.ingested.length > 0 || promote.review.length > 0);
  const attempted = !loading && progress.length > 0;

  const runLoad = async () => {
    const srcs = deep.sources;
    if (!srcs.length || loading) return;
    setLoading(true);
    setProgress(srcs.map((s) => ({ title: s.title, status: 'pending' as ProgStatus })));
    const ingested: TrustedSource[] = [];
    const review: TrustedSource[] = [];
    for (let i = 0; i < srcs.length; i++) {
      const s = srcs[i];
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
        // publish incrementally so the review actions appear as low-trust sources arrive
        setDeep({ promote: { ingested: [...ingested], review: [...review] } });
      } catch {
        setProgress((p) => p.map((it, j) => (j === i ? { ...it, status: 'error' } : it)));
      }
    }
    setLoading(false);
  };

  const doneCount = progress.filter((p) => p.status !== 'pending' && p.status !== 'loading').length;
  // Read the live promote from the store (not the render snapshot) so two in-flight decisions
  // can't clobber each other. keep=true → move to «в графе»; keep=false → drop from review.
  const decide = (id: string, keep: boolean) => {
    const cur = useStore.getState().deep.promote as PromoteResult | null;
    if (!cur) return;
    const moved = cur.review.find((x) => x.id === id);
    setDeep({
      promote: {
        ingested: keep && moved ? [...cur.ingested, moved] : cur.ingested,
        review: cur.review.filter((x) => x.id !== id),
      },
    });
  };
  const approve = useMutation({
    mutationFn: (id: string) => api.approveSource(id),
    onMutate: (id) => withBusy(id, true),
    onSettled: (_r, _e, id) => withBusy(id, false),
    onSuccess: (_r, id) => decide(id, true),
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
          <ShieldCheck size={14} className="text-copper" /> Доверие к источникам · найдено {deep.sources.length}
        </div>
        {loading ? (
          <span className="flex items-center gap-1.5 rounded bg-copper/15 px-2.5 py-1 text-xs text-copper opacity-80">
            <Loader2 size={13} className="animate-spin" />
            Загрузка {doneCount}/{deep.sources.length}…
          </span>
        ) : hasResult ? (
          // Succeeded — no button, so the user can't re-trigger a second ingest.
          <span className="flex items-center gap-1 text-[11px] text-verified">
            <Check size={13} /> загружено
          </span>
        ) : (
          <button
            onClick={() => void runLoad()}
            className="flex items-center gap-1.5 rounded bg-copper/15 px-2.5 py-1 text-xs text-copper hover:bg-copper/25"
          >
            <DatabaseZap size={13} />
            {attempted ? 'Повторить' : 'Загрузить в граф'}
          </button>
        )}
      </div>

      {/* Live per-source loading queue — pending → loading → в графе / на ревью */}
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
                    p.status === 'review' ? 'text-gap' : p.status === 'error' ? 'text-contradiction' : 'text-faint'
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
                {promote.ingested.map((r, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 rounded border border-line/60 px-2.5 py-1.5 text-[12px]"
                  >
                    <Check size={12} className="shrink-0 text-verified" />
                    {r.url ? (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex min-w-0 items-center gap-1 text-ink hover:text-copper"
                        title={r.url}
                      >
                        <span className="truncate">{r.title}</span>
                        <ExternalLink size={11} className="shrink-0 opacity-60" />
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
                ))}
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
                  // Only trust http(s) — a web-search URL could be javascript:/data: (DOM-XSS).
                  const safeUrl = /^https?:\/\//i.test((r.url ?? '').trim()) ? r.url : '';
                  const isBusy = busy.has(r.id ?? '');
                  return (
                    <div
                      key={r.id}
                      className="rounded border border-gap/30 bg-graphite/20 px-2.5 py-2 text-[12px]"
                    >
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
                              <ExternalLink size={11} className="shrink-0 opacity-60" />
                            </a>
                          ) : (
                            <span className="truncate font-medium text-ink">{r.title}</span>
                          )}
                          {safeUrl && (
                            <div className="mt-0.5 truncate font-mono text-[10px] text-faint">
                              {hostOf(safeUrl)}
                            </div>
                          )}
                        </div>
                        <span className="flex shrink-0 items-center gap-1">
                          <button
                            onClick={() => r.id && approve.mutate(r.id)}
                            disabled={isBusy}
                            className="flex items-center gap-1 rounded bg-verified/15 px-2 py-1 text-[11px] text-verified hover:bg-verified/25 disabled:opacity-50"
                            title="Добавить источник в корпус"
                          >
                            <Check size={12} /> Добавить
                          </button>
                          <button
                            onClick={() => r.id && reject.mutate(r.id)}
                            disabled={isBusy}
                            className="flex items-center gap-1 rounded bg-contradiction/15 px-2 py-1 text-[11px] text-contradiction hover:bg-contradiction/25 disabled:opacity-50"
                            title="Не добавлять"
                          >
                            <X size={12} /> Пропустить
                          </button>
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className={`chip ${trustChip(r.trust.trust_tier)}`}>
                          доверие: {r.trust.trust_tier} {r.trust.trust_score.toFixed(2)}
                        </span>
                        <span className={`chip ${freshChip(r.trust.freshness)}`}>
                          {freshLabel(r.trust.freshness)}
                        </span>
                        {r.year != null && (
                          <span className="chip border-line/60 text-faint">{r.year}</span>
                        )}
                      </div>
                      {warnings.length > 0 && (
                        <ul className="mt-1.5 space-y-0.5">
                          {warnings.map((w, i) => (
                            <li key={i} className="flex gap-1.5 text-[11px] text-gap">
                              <TriangleAlert size={11} className="mt-0.5 shrink-0" />
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

function ManualAddForm({ onAdded }: { onAdded: () => void }) {
  const [f, setF] = useState({ title: '', authors: '', year: '', doi: '', url: '', source: 'manual', abstract: '', domain: '' });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));
  const add = useMutation({
    mutationFn: () =>
      api.addArticle({
        title: f.title.trim(),
        authors: f.authors ? f.authors.split(',').map((a) => a.trim()).filter(Boolean) : [],
        year: f.year ? Number(f.year) : null,
        doi: f.doi.trim(),
        url: f.url.trim(),
        source: f.source,
        abstract: f.abstract.trim(),
        domain: f.domain.trim(),
      }),
    onSuccess: () => {
      setF({ title: '', authors: '', year: '', doi: '', url: '', source: 'manual', abstract: '', domain: '' });
      onAdded();
    },
  });

  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-nickel">
        <BookPlus size={15} className="text-copper" /> Добавить статью в базу вручную
      </div>
      <div className="space-y-2">
        <input value={f.title} onChange={set('title')} placeholder="Название статьи *"
          className="w-full rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50" />
        <input value={f.authors} onChange={set('authors')} placeholder="Авторы (через запятую)"
          className="w-full rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50" />
        <div className="grid grid-cols-3 gap-2">
          <input value={f.year} onChange={set('year')} placeholder="Год" inputMode="numeric"
            className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50" />
          <input value={f.doi} onChange={set('doi')} placeholder="DOI"
            className="col-span-2 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50" />
        </div>
        <input value={f.url} onChange={set('url')} placeholder="URL источника"
          className="w-full rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50" />
        <textarea value={f.abstract} onChange={set('abstract')} rows={3} placeholder="Аннотация статьи"
          className="w-full resize-none rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50" />
      </div>
      <button
        onClick={() => f.title.trim() && add.mutate()}
        disabled={add.isPending || !f.title.trim()}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-copper/40 bg-copper/10 px-4 py-2.5 text-sm text-copper transition hover:bg-copper/20 disabled:opacity-50"
      >
        {add.isPending ? <Loader2 size={15} className="animate-spin" /> : <BookPlus size={15} />}
        Добавить в граф
      </button>
      {add.isSuccess && (
        <div className="mt-2 text-xs text-verified">
          ✓ Добавлено: {add.data.paper_id} ({add.data.nodes} узлов, {add.data.edges} связей)
        </div>
      )}
      {add.isError && <div className="mt-2 text-xs text-contradiction">{String(add.error)}</div>}
    </div>
  );
}
