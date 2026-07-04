import { useState } from 'react';
import { BookMarked, Filter } from 'lucide-react';
import { FacetSearchView } from './FacetSearchView';
import { GlossaryView } from './GlossaryView';

// «Поиск по корпусу» — единый раздел вместо трёх пунктов меню: фасетный поиск
// (категориальные фильтры), диапазонные фасеты (числовые гистограммы + слайдеры) и
// глоссарий (RU/EN словарь терминов). Табы, а не мердж логики: каждый под-экран
// рендерится как есть (все трое заполняют h-full и скроллятся внутри своей области),
// поэтому поведение и код компонентов не меняются.

type Tab = 'facets' | 'glossary';

const TABS: { id: Tab; label: string; icon: typeof Filter }[] = [
  { id: 'facets', label: 'Фасетный поиск', icon: Filter },
  { id: 'glossary', label: 'Глоссарий', icon: BookMarked },
];

export function CorpusExplorerView() {
  const [tab, setTab] = useState<Tab>('facets');

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line px-6 pt-4">
        <div className="eyebrow mb-2">поиск и словарь по корпусу</div>
        <div className="flex flex-wrap gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
                  active
                    ? 'border-copper text-copper'
                    : 'border-transparent text-faint hover:text-ink'
                }`}
              >
                <Icon size={14} /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {tab === 'facets' && <FacetSearchView />}
        {tab === 'glossary' && <GlossaryView />}
      </div>
    </div>
  );
}
