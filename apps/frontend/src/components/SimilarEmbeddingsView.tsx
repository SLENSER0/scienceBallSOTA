import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Boxes, Cpu, Search, Sparkles, TriangleAlert, Waypoints } from 'lucide-react';
import { api } from '../api';

// §3.13 — «Похожие материалы/режимы» через vector-search по node-embeddings.
// Семантические аналоги сущности (или свободного запроса) по косинусной близости
// эмбеддингов — «найди сплавы/режимы, похожие на этот» одним кликом. Отличается от
// топологического (Jaccard, «Вероятные связи») и фасетного сходства: близкими
// становятся сущности со схожим описанием, даже если в графе они не связаны.

type Mode = 'entity' | 'query';

const LABEL_RU: Record<string, string> = {
  Material: 'материалы',
  Alloy: 'сплавы',
  ProcessingRegime: 'режимы',
  TechnologySolution: 'решения',
  Property: 'свойства',
  Method: 'методы',
  Equipment: 'оборудование',
  ChemicalElement: 'элементы',
  Facility: 'объекты',
  Lab: 'лаборатории',
  Person: 'люди',
  Geography: 'география',
};

function labelRu(l: string): string {
  return LABEL_RU[l] ?? l;
}

function ResultRow({
  hit,
  onPick,
}: {
  hit: { id: string; name: string; label: string; similarity: number; reason: string };
  onPick?: (id: string) => void;
}) {
  const pct = Math.max(3, Math.round(hit.similarity * 100));
  return (
    <li
      className={`rounded-lg border border-line bg-surface/50 px-4 py-3 transition hover:border-copper/40 ${
        onPick ? 'cursor-pointer' : ''
      }`}
      onClick={onPick ? () => onPick(hit.id) : undefined}
      title={onPick ? 'Искать похожие на эту сущность' : undefined}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Boxes size={15} className="shrink-0 text-copper" />
          <span className="truncate font-medium text-ink">{hit.name || hit.id}</span>
          <span className="shrink-0 font-mono text-[10px] text-faint">[{hit.label}]</span>
        </div>
        <span className="metric shrink-0 text-sm text-nickel-bright">{pct}%</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-line/60">
        <div className="h-full rounded-full bg-copper/70" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-2 flex items-start gap-1.5 text-[11px] text-faint">
        <Sparkles size={12} className="mt-0.5 shrink-0 text-copper/80" />
        <span>{hit.reason}</span>
      </div>
    </li>
  );
}

export function SimilarEmbeddingsView() {
  const [mode, setMode] = useState<Mode>('entity');
  const [label, setLabel] = useState<string>('Material');
  const [seed, setSeed] = useState('');
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState('');

  const status = useQuery({ queryKey: ['se-status'], queryFn: () => api.similarEmbStatus() });
  const seeds = useQuery({
    queryKey: ['se-seeds', label],
    queryFn: () => api.similarEmbSeeds(label || undefined),
  });

  const seedId = seed || seeds.data?.seeds[0]?.id || '';
  const labels = seeds.data?.labels ?? status.data?.labels ?? [];

  const sim = useQuery({
    queryKey: ['se-similar', seedId],
    queryFn: () => api.similarEmbSimilar(seedId),
    enabled: mode === 'entity' && !!seedId,
  });

  const byText = useQuery({
    queryKey: ['se-bytext', submitted],
    queryFn: () => api.similarEmbByText(submitted),
    enabled: mode === 'query' && submitted.trim().length > 0,
  });

  const active = mode === 'entity' ? sim : byText;
  const method = active.data?.method;
  const seedName = useMemo(
    () => seeds.data?.seeds.find((s) => s.id === seedId)?.name || seedId,
    [seeds.data, seedId],
  );

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">семантические аналоги</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Похожие материалы и режимы</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          Находим сущности, близкие по смыслу к выбранной — «найди аналоги этого сплава или режима». В отличие от «Вероятных связей»
          (общие соседи в графе) здесь близкими становятся даже никак не соединённые узлы со
          схожим смыслом.
        </p>

        {/* mode tabs */}
        <div className="mb-4 inline-flex rounded-lg border border-line bg-surface/40 p-0.5 text-sm">
          <button
            onClick={() => setMode('entity')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              mode === 'entity' ? 'bg-copper/15 text-copper' : 'text-faint hover:text-ink'
            }`}
          >
            <Boxes size={14} /> По сущности
          </button>
          <button
            onClick={() => setMode('query')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              mode === 'query' ? 'bg-copper/15 text-copper' : 'text-faint hover:text-ink'
            }`}
          >
            <Search size={14} /> По запросу
          </button>
        </div>

        {/* controls */}
        {mode === 'entity' ? (
          <div className="mb-5 flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wide text-faint">Тип</span>
              <select
                value={label}
                onChange={(e) => {
                  setLabel(e.target.value);
                  setSeed('');
                }}
                className="rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
              >
                <option value="">Все типы</option>
                {labels.map((l) => (
                  <option key={l} value={l}>
                    {labelRu(l)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wide text-faint">Сущность</span>
              <select
                value={seedId}
                onChange={(e) => setSeed(e.target.value)}
                className="min-w-64 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
              >
                {seeds.data?.seeds.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || s.id}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSubmitted(text);
            }}
            className="mb-5 flex flex-wrap items-end gap-3"
          >
            <label className="flex flex-1 flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wide text-faint">Запрос</span>
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="напр. износостойкий сплав для бурового долота"
                className="min-w-72 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={!text.trim()}
              className="rounded-md border border-copper/50 bg-copper/15 px-4 py-2 text-sm text-copper transition hover:bg-copper/25 disabled:opacity-40"
            >
              Найти аналоги
            </button>
          </form>
        )}

        {method && (
          <div className="mb-4 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/50 px-2.5 py-1 text-[10px] uppercase tracking-wide text-faint">
              <Cpu size={11} className="text-copper" />
              {method === 'entity_index' ? 'поиск по смыслу' : 'поиск по запросу'}
            </span>
            {mode === 'entity' && seedName && (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-faint">
                <Waypoints size={12} className="text-copper" /> аналоги «{seedName}»
              </span>
            )}
          </div>
        )}

        {active.isLoading && (
          <div className="text-sm text-faint">Ищем аналоги…</div>
        )}
        {active.isError && (
          <div className="flex items-center gap-2 text-sm text-copper">
            <TriangleAlert size={15} /> Не удалось получить аналоги.
          </div>
        )}

        {active.data && active.data.count === 0 && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            {mode === 'query'
              ? 'Ничего похожего по смыслу не нашлось.'
              : 'У этой сущности нет описания для сравнения.'}
          </div>
        )}

        {active.data && active.data.count > 0 && (
          <>
            <ul className="space-y-2">
              {active.data.similar.map((h) => (
                <ResultRow
                  key={h.id}
                  hit={h}
                  onPick={
                    mode === 'entity'
                      ? (id) => {
                          setSeed(id);
                        }
                      : undefined
                  }
                />
              ))}
            </ul>
            <div className="mt-4 flex items-center gap-1.5 text-[11px] text-faint">
              <Sparkles size={12} className="text-copper" /> {active.data.count} семантических
              аналогов
            </div>
          </>
        )}
      </div>
    </div>
  );
}
