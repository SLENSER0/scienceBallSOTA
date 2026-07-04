import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookPlus,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  DatabaseZap,
  ExternalLink,
  FlaskConical,
  ImagePlus,
  Library,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  X,
} from 'lucide-react';
import { api, type TrustedSource } from '../api';
import { useStore } from '../store';
import { CallHistory } from './CallHistory';
import { pushCall } from '../lib/callHistory';
import { DocumentUpload } from './DocumentUpload';
import { MultimodalPanel } from './MultimodalPanel';
import { TabHub } from './TabHub';
import { SourcesShowcaseView } from './SourcesShowcaseView';

// «Библиотека» — add scientific articles to the graph. Two flows:
// (1) deep-research: decompose a question into sub-questions × ready-to-open
//     search links across the scientific source catalog (open_deep_research-style);
// (2) manual add: a form that writes a :Paper (+ abstract chunk/evidence) to the graph.

const ACCESS_STYLE: Record<string, { label: string; cls: string }> = {
  open: { label: 'открытый', cls: 'text-verified border-verified/40' },
  paywalled: { label: 'платный', cls: 'text-copper border-copper/40' },
  shadow: { label: 'теневая б-ка', cls: 'text-contradiction border-contradiction/40' },
};

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
  const [question, setQuestion] = useState('');
  const sources = useQuery({ queryKey: ['research-sources'], queryFn: api.researchSources });
  const recent = useQuery({ queryKey: ['recent-articles'], queryFn: api.recentArticles });
  const deepStatus = useQuery({ queryKey: ['deep-status'], queryFn: api.deepStatus });

  const plan = useMutation({ mutationFn: (q: string) => api.researchPlan(q) });

  // Deep research streams into the app-level store (survives tab switches).
  const deep = useStore((s) => s.deep);
  const setDeep = useStore((s) => s.setDeep);
  const resetDeep = useStore((s) => s.resetDeep);
  const esRef = useRef<EventSource | null>(null);

  const startDeep = (q: string) => {
    if (q.trim()) pushCall('deep-research', q.trim());
    esRef.current?.close();
    resetDeep(q);
    const es = new EventSource(`/api/v1/research/deep/stream?question=${encodeURIComponent(q)}`);
    esRef.current = es;
    es.addEventListener('stage', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setDeep({ stages: [...useStore.getState().deep.stages, { node: d.node, label: d.label }] });
    });
    es.addEventListener('reasoning', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setDeep({ reasoning: `${useStore.getState().deep.reasoning}\n\n### ${d.node}\n${d.text}` });
    });
    es.addEventListener('token', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setDeep({ tokens: useStore.getState().deep.tokens + (d.text ?? '') });
    });
    es.addEventListener('report', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setDeep({ report: d.text ?? '' });
    });
    es.addEventListener('sources', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setDeep({ sources: d.items ?? [] });
    });
    es.addEventListener('done', () => {
      setDeep({ running: false });
      es.close();
    });
    es.addEventListener('error', (e) => {
      const msg = (e as MessageEvent).data ? JSON.parse((e as MessageEvent).data).message : 'stream error';
      setDeep({ running: false, error: String(msg) });
      es.close();
    });
  };

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

        {/* Deep-research search */}
        <div className="panel mt-5 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
            <Sparkles size={15} className="text-copper" /> Deep-research по источникам
          </div>
          <div className="flex gap-2">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && question.trim() && plan.mutate(question)}
              placeholder="Напр.: очистка шахтных вод от сульфатов"
              className="flex-1 rounded-md border border-line bg-surface/60 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
            />
            <button
              onClick={() => question.trim() && plan.mutate(question)}
              disabled={plan.isPending || !question.trim()}
              className="flex items-center gap-2 rounded-md bg-copper/20 px-4 text-sm text-copper transition enabled:hover:bg-copper/30 disabled:opacity-40"
              title="Быстрый поиск: ссылки по базам"
            >
              {plan.isPending ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
              Ссылки
            </button>
            <button
              onClick={() => question.trim() && startDeep(question)}
              disabled={deep.running || !question.trim() || !deepStatus.data?.available}
              className="flex items-center gap-2 rounded-md border border-copper/40 bg-copper/10 px-4 text-sm text-copper transition enabled:hover:bg-copper/20 disabled:opacity-40"
              title={deepStatus.data?.available ? 'Глубокое исследование по реальным веб-источникам (~2-3 мин)' : 'Сейчас недоступно'}
            >
              {deep.running ? <Loader2 size={15} className="animate-spin" /> : <Brain size={15} />}
              Deep-research
            </button>
          </div>

          {!deep.running && (
            <CallHistory
              feature="deep-research"
              title="История deep-research"
              onPick={(e) => {
                setQuestion(e.label);
                startDeep(e.label);
              }}
            />
          )}
          <DeepResearchPanel />
          {deep.error && (
            <div className="mt-2 text-xs text-contradiction">Ошибка: {deep.error}</div>
          )}

          {plan.data && (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-1.5">
                {plan.data.keywords.map((k) => (
                  <span key={k} className="chip text-faint">{k}</span>
                ))}
              </div>
              {plan.data.sub_questions.map((sq, i) => (
                <div key={i} className="rounded-md border border-line bg-surface/40 p-3">
                  <div className="mb-2 text-sm font-medium text-ink">{sq.text}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {sq.links.map((l) => {
                      const a = ACCESS_STYLE[l.access] ?? ACCESS_STYLE.paywalled;
                      return (
                        <a
                          key={l.source_id}
                          href={l.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`flex items-center gap-1 rounded border px-2 py-1 text-xs transition hover:bg-surface ${a.cls}`}
                          title={`${l.source_name} · ${a.label}`}
                        >
                          {l.access === 'shadow' && <TriangleAlert size={11} />}
                          {l.source_name}
                          <ExternalLink size={10} className="opacity-60" />
                        </a>
                      );
                    })}
                  </div>
                </div>
              ))}
              <p className="text-[11px] text-faint">
                Ссылки открываются во внешних базах. Sci-Hub — теневая библиотека (правовая
                серая зона); система ничего не скачивает автоматически, решение за вами.
              </p>
            </div>
          )}
        </div>

        {/* Upload document → graph + viewer (§17.19) */}
        <DocumentUpload />

        {/* Multimodal analysis — figures/micrographs/flowsheets (minimax-m3) */}
        <MultimodalPanel />

        {/* Two columns: manual add + recent */}
        <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <ManualAddForm onAdded={() => void qc.invalidateQueries({ queryKey: ['recent-articles'] })} />
          <div className="panel p-4">
            <div className="mb-2 flex items-center gap-2 text-sm text-nickel">
              <FlaskConical size={15} className="text-copper" /> Недавно добавленные
            </div>
            {recent.data?.articles.length ? (
              <ul className="space-y-2">
                {recent.data.articles.map((a) => (
                  <li key={a.id} className="text-sm">
                    <span className="text-ink">{a.title}</span>
                    <span className="ml-1 font-mono text-[10px] text-faint">
                      {a.year ?? ''} {a.doi ? `· ${a.doi}` : ''}
                    </span>
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

// open-webui-style deep-research trace: live stage pipeline + a collapsible
// «Рассуждение» panel that streams the model's thinking, then the final report.
function DeepResearchPanel() {
  const deep = useStore((s) => s.deep);
  const [showReasoning, setShowReasoning] = useState(true);
  if (!deep.question && !deep.running) return null;

  const live = deep.reasoning || deep.tokens;
  return (
    <div className="mt-4 rounded-md border border-copper/30 bg-surface/40 p-4">
      <div className="mb-3 flex items-center gap-2 text-xs text-faint">
        <Brain size={14} className="text-copper" />
        Реальный веб-поиск по научным источникам
        {deep.running && <Loader2 size={12} className="animate-spin text-copper" />}
      </div>

      {/* Stage pipeline */}
      {deep.stages.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {deep.stages.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              <span
                className={`rounded px-2 py-0.5 text-[11px] ${
                  i === deep.stages.length - 1 && deep.running
                    ? 'bg-copper/20 text-copper'
                    : 'bg-surface text-nickel'
                }`}
              >
                {s.label}
              </span>
              {i < deep.stages.length - 1 && <ChevronRight size={11} className="text-faint" />}
            </span>
          ))}
        </div>
      )}

      {/* Reasoning (collapsible «thinking») */}
      {live && (
        <div className="mb-3 rounded border border-line bg-graphite/40">
          <button
            onClick={() => setShowReasoning((v) => !v)}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs text-faint hover:text-nickel"
          >
            {showReasoning ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {deep.running ? 'Рассуждение (в реальном времени)…' : 'Рассуждение'}
          </button>
          {showReasoning && (
            <div className="max-h-56 overflow-y-auto whitespace-pre-wrap border-t border-line px-3 py-2 font-mono text-[11px] leading-relaxed text-muted">
              {deep.reasoning}
              {deep.running && deep.tokens && (
                <span className="text-faint">{deep.tokens.slice(-1200)}</span>
              )}
              {deep.running && <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-copper/70 align-middle" />}
            </div>
          )}
        </div>
      )}

      {/* Final report */}
      {deep.report && (
        <div className="md max-h-[440px] overflow-y-auto rounded border border-line bg-graphite/30 p-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{deep.report}</ReactMarkdown>
        </div>
      )}
      {deep.running && !deep.report && (
        <div className="font-mono text-[11px] text-faint">
          Анализ источников… отчёт появится по завершении (~2-3 мин).
        </div>
      )}

      {/* «Загрузить в граф» + Source Trust gate + low-trust review */}
      {!deep.running && deep.sources.length > 0 && <LoadToGraphPanel />}
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
    onSuccess: (r) => setDeep({ report: r.report, sources: r.sources }),
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

// «Загрузить в граф»: run each found source through Source Trust, ingest the trusted
// ones and hold the low-trust ones for the user's add/reject decision (§23.27).
function LoadToGraphPanel() {
  const deep = useStore((s) => s.deep);
  const setDeep = useStore((s) => s.setDeep);
  const promote = deep.promote as PromoteResult | null;

  const load = useMutation({
    mutationFn: () =>
      api.promoteDeepSources(
        deep.sources.map((s) => ({ title: s.title, url: s.url, snippet: s.snippet, year: s.year ?? null })),
      ),
    onSuccess: (r) => setDeep({ promote: r }),
  });
  const approve = useMutation({
    mutationFn: (id: string) => api.approveSource(id),
    onSuccess: (_r, id) => {
      if (!promote) return;
      const moved = promote.review.find((x) => x.id === id);
      setDeep({
        promote: {
          ingested: moved ? [...promote.ingested, moved] : promote.ingested,
          review: promote.review.filter((x) => x.id !== id),
        },
      });
    },
  });
  const reject = useMutation({
    mutationFn: (id: string) => api.rejectSource(id),
    onSuccess: (_r, id) => {
      if (!promote) return;
      setDeep({ promote: { ...promote, review: promote.review.filter((x) => x.id !== id) } });
    },
  });

  return (
    <div className="mt-3 rounded border border-copper/30 bg-surface/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs text-nickel">
          <ShieldCheck size={14} className="text-copper" /> Доверие к источникам · найдено {deep.sources.length}
        </div>
        <button
          onClick={() => load.mutate()}
          disabled={load.isPending}
          className="flex items-center gap-1.5 rounded bg-copper/15 px-2.5 py-1 text-xs text-copper hover:bg-copper/25 disabled:opacity-50"
        >
          {load.isPending ? <Loader2 size={13} className="animate-spin" /> : <DatabaseZap size={13} />}
          Загрузить в граф
        </button>
      </div>
      {load.isError && <div className="text-[11px] text-contradiction">не удалось загрузить</div>}

      {promote && (
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
                    <span className="truncate text-ink">{r.title}</span>
                    <span className={`chip ${trustChip(r.trust.trust_tier)}`}>
                      {r.trust.trust_tier} {r.trust.trust_score.toFixed(2)}
                    </span>
                    <span className="ml-auto font-mono text-[10px] text-faint">{r.trust.freshness}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {promote.review.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-gap">
                на ревью — низкое доверие ({promote.review.length})
              </div>
              <div className="space-y-1.5">
                {promote.review.map((r) => (
                  <div
                    key={r.id}
                    className="flex items-center gap-2 rounded border border-gap/30 px-2.5 py-1.5 text-[12px]"
                  >
                    <span className="truncate text-ink" title={(r.trust.warnings ?? []).join(' · ')}>
                      {r.title}
                    </span>
                    <span className={`chip ${trustChip(r.trust.trust_tier)}`}>
                      {r.trust.trust_tier} {r.trust.trust_score.toFixed(2)}
                    </span>
                    <span className="ml-auto flex items-center gap-1">
                      <button
                        onClick={() => r.id && approve.mutate(r.id)}
                        disabled={approve.isPending}
                        className="rounded bg-verified/15 p-1 text-verified hover:bg-verified/25 disabled:opacity-50"
                        title="Добавить в корпус"
                      >
                        <Check size={13} />
                      </button>
                      <button
                        onClick={() => r.id && reject.mutate(r.id)}
                        disabled={reject.isPending}
                        className="rounded bg-contradiction/15 p-1 text-contradiction hover:bg-contradiction/25 disabled:opacity-50"
                        title="Отклонить"
                      >
                        <X size={13} />
                      </button>
                    </span>
                  </div>
                ))}
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
