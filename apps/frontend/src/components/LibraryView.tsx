import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookPlus,
  Brain,
  ExternalLink,
  FlaskConical,
  Loader2,
  Search,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import { api } from '../api';

// «Библиотека» — add scientific articles to the graph. Two flows:
// (1) deep-research: decompose a question into sub-questions × ready-to-open
//     search links across the scientific source catalog (open_deep_research-style);
// (2) manual add: a form that writes a :Paper (+ abstract chunk/evidence) to the graph.

const ACCESS_STYLE: Record<string, { label: string; cls: string }> = {
  open: { label: 'открытый', cls: 'text-verified border-verified/40' },
  paywalled: { label: 'платный', cls: 'text-copper border-copper/40' },
  shadow: { label: 'теневая б-ка', cls: 'text-contradiction border-contradiction/40' },
};

export function LibraryView() {
  const qc = useQueryClient();
  const [question, setQuestion] = useState('');
  const sources = useQuery({ queryKey: ['research-sources'], queryFn: api.researchSources });
  const recent = useQuery({ queryKey: ['recent-articles'], queryFn: api.recentArticles });
  const deepStatus = useQuery({ queryKey: ['deep-status'], queryFn: api.deepStatus });

  const plan = useMutation({ mutationFn: (q: string) => api.researchPlan(q) });
  const deep = useMutation({ mutationFn: (q: string) => api.deepResearch(q) });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">Библиотека · добавление статей</div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Найти и добавить научные статьи
        </h1>
        <p className="mt-1 text-sm text-faint">
          Deep-research разбивает вопрос на под-вопросы и строит ссылки на поиск по научным базам.
          Найденную статью добавьте в граф вручную формой ниже.
        </p>

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
              onClick={() => question.trim() && deep.mutate(question)}
              disabled={deep.isPending || !question.trim() || !deepStatus.data?.available}
              className="flex items-center gap-2 rounded-md border border-copper/40 bg-copper/10 px-4 text-sm text-copper transition enabled:hover:bg-copper/20 disabled:opacity-40"
              title={deepStatus.data?.available ? 'Deep-research (open_deep_research на OSS-LLM, ~1-2 мин)' : 'Движок недоступен'}
            >
              {deep.isPending ? <Loader2 size={15} className="animate-spin" /> : <Brain size={15} />}
              Deep-research
            </button>
          </div>

          {deep.isPending && (
            <div className="mt-3 flex items-center gap-2 font-mono text-xs text-faint">
              <Loader2 size={13} className="animate-spin text-copper" />
              open_deep_research анализирует источники (clarify → brief → research → отчёт)…
            </div>
          )}
          {deep.data?.report && (
            <div className="mt-4 rounded-md border border-copper/30 bg-surface/40 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs text-faint">
                <Brain size={13} className="text-copper" />
                open_deep_research · {deep.data.model ?? deep.data.engine}
              </div>
              <div className="md max-h-[420px] overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{deep.data.report}</ReactMarkdown>
              </div>
            </div>
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
        <textarea value={f.abstract} onChange={set('abstract')} rows={3} placeholder="Аннотация (станет Evidence в графе)"
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
