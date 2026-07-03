import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Bookmark, Loader2 } from 'lucide-react';
import { api } from '../api';
import { useStore } from '../store';
import { AnswerView } from './AnswerView';
import { GraphPanel } from './GraphPanel';

const EXAMPLES = [
  'Какие методы обессоливания воды подходят для обогатительной фабрики, если сульфаты, хлориды, Ca, Mg, Na по 200–300 мг/л, а сухой остаток ≤1000 мг/дм³?',
  'Какие технические решения циркуляции католита при электроэкстракции никеля в мировой практике, и какая скорость потока оптимальна?',
  'Распределение Au, Ag и МПГ между медным/никелевым штейном и шлаком за последние 5 лет',
  'Способы закачки шахтных вод в глубокие горизонты в России и за рубежом, технико-экономические показатели',
];

const GEO_OPTIONS = [
  { id: 'all', label: 'Вся практика' },
  { id: 'russia', label: 'Отечественная' },
  { id: 'foreign', label: 'Зарубежная' },
];

export function AskView() {
  const { role, useLlm, answer, setAnswer, setSelectedNode } = useStore();
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [geo, setGeo] = useState('all');

  const views = useQuery({ queryKey: ['saved-views'], queryFn: api.listViews });
  const saveView = useMutation({
    mutationFn: (payload: { query: string; geography: string }) =>
      api.saveView(payload.query.slice(0, 60), payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['saved-views'] }),
  });

  const ask = useMutation({
    mutationFn: (query: string) => api.query(query, { role, useLlm, geography: geo }),
    onSuccess: (a) => {
      setAnswer(a);
      setSelectedNode(null);
    },
  });

  const submit = (text: string) => {
    if (text.trim()) ask.mutate(text.trim());
  };

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[1fr,minmax(360px,42%)]">
      {/* Left: query + answer */}
      <section className="flex min-h-0 flex-col overflow-y-auto px-6 py-5">
        <div className="mx-auto w-full max-w-3xl">
          <div className="panel p-1.5 shadow-panel focus-within:shadow-molten">
            <div className="flex items-end gap-2">
              <textarea
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(q);
                }}
                rows={2}
                placeholder="Задайте инженерный вопрос: материал + процесс + условия + числа + география…"
                className="min-h-[52px] flex-1 resize-none bg-transparent px-3 py-2 text-[15px] leading-snug text-ink placeholder:text-faint focus:outline-none"
              />
              <button
                onClick={() => submit(q)}
                disabled={ask.isPending || !q.trim()}
                className="btn-copper mb-1 mr-1 flex items-center gap-1.5"
              >
                {ask.isPending ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                <span className="hidden sm:inline">Распутать</span>
              </button>
            </div>
          </div>

          {/* Geographic filter — отечественная / зарубежная практика */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wide text-faint">практика:</span>
            <div className="flex overflow-hidden rounded-md border border-line">
              {GEO_OPTIONS.map((o) => (
                <button
                  key={o.id}
                  onClick={() => {
                    setGeo(o.id);
                    if (answer && q.trim()) submit(q);
                  }}
                  className={`px-2.5 py-1 text-[11px] transition ${
                    geo === o.id ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {q.trim() && (
              <button
                onClick={() => saveView.mutate({ query: q.trim(), geography: geo })}
                disabled={saveView.isPending}
                className="chip ml-auto text-faint hover:border-copper/40 hover:text-copper disabled:opacity-40"
                title="Сохранить запрос как вид"
              >
                <Bookmark size={12} /> Сохранить вид
              </button>
            )}
          </div>

          {!answer && !ask.isPending && (
            <div className="mt-6">
              <div className="eyebrow mb-2">Демо-вопросы постановки</div>
              <div className="flex flex-col gap-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => {
                      setQ(ex);
                      submit(ex);
                    }}
                    className="group rounded-md border border-line bg-surface/40 px-3 py-2.5 text-left text-sm text-muted transition-colors hover:border-copper/40 hover:text-ink"
                  >
                    <ArrowRight
                      size={13}
                      className="mr-2 inline text-faint transition-colors group-hover:text-copper"
                    />
                    {ex}
                  </button>
                ))}
              </div>

              {(views.data?.views.length ?? 0) > 0 && (
                <div className="mt-6">
                  <div className="eyebrow mb-2 flex items-center gap-1.5">
                    <Bookmark size={12} /> Сохранённые виды
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {views.data!.views.map((v) => {
                      const query = String(v.payload.query ?? v.name);
                      return (
                        <button
                          key={v.view_id}
                          onClick={() => {
                            setQ(query);
                            if (typeof v.payload.geography === 'string') setGeo(v.payload.geography);
                            submit(query);
                          }}
                          className="chip max-w-xs truncate text-muted hover:border-copper/40 hover:text-copper"
                          title={query}
                        >
                          {v.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {ask.isError && (
            <div className="mt-4 rounded-md border border-contradiction/40 bg-contradiction/10 px-4 py-3 text-sm text-contradiction">
              Не удалось получить ответ. Проверьте, запущен ли API (:8000).
            </div>
          )}

          {ask.isPending && (
            <div className="mt-8 flex items-center gap-3 text-muted">
              <Loader2 size={18} className="animate-spin text-copper" />
              <span className="font-mono text-sm">
                Распутываю клубок: разбор запроса → поиск фактов → синтез с доказательствами…
              </span>
            </div>
          )}

          {answer && !ask.isPending && <AnswerView answer={answer} />}
        </div>
      </section>

      {/* Right: the клубок */}
      <section className="hidden min-h-0 border-l border-line bg-graphite/40 lg:flex lg:flex-col">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <div className="eyebrow">Клубок знаний · подграф ответа</div>
          <GraphLegend />
        </div>
        <div className="min-h-0 flex-1">
          {answer?.graph ? (
            <GraphPanel data={answer.graph} onSelect={setSelectedNode} selectedId={useStore.getState().selectedNode?.id} />
          ) : (
            <div className="flex h-full items-center justify-center text-faint font-mono text-sm">
              граф появится после запроса
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function GraphLegend() {
  const items = [
    ['#C87941', 'решение'],
    ['#8FA3B0', 'материал'],
    ['#E0A23C', 'пробел'],
    ['#E5484D', 'противоречие'],
  ];
  return (
    <div className="flex gap-3">
      {items.map(([c, l]) => (
        <span key={l} className="flex items-center gap-1 font-mono text-[10px] text-faint">
          <span className="h-2 w-2 rounded-full" style={{ background: c }} />
          {l}
        </span>
      ))}
    </div>
  );
}
