import { useQuery } from '@tanstack/react-query';
import { CircleHelp, LayoutGrid, Network, BookMarked } from 'lucide-react';
import { api } from './api';
import { useStore, type View } from './store';
import { AskView } from './components/AskView';
import { CoverageView } from './components/CoverageView';
import { GlossaryView } from './components/GlossaryView';
import { EvidenceDrawer } from './components/EvidenceDrawer';

const NAV: { id: View; label: string; icon: typeof Network }[] = [
  { id: 'ask', label: 'Запрос', icon: Network },
  { id: 'coverage', label: 'Покрытие', icon: LayoutGrid },
  { id: 'glossary', label: 'Глоссарий', icon: BookMarked },
];

export function App() {
  const { view, setView, role, setRole, useLlm, setUseLlm } = useStore();
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats });

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left rail */}
      <aside className="flex w-16 shrink-0 flex-col items-center border-r border-line bg-graphite/60 py-4">
        <div className="mb-6 flex h-9 w-9 items-center justify-center rounded-md bg-copper/15 text-copper">
          <ClubokMark />
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              title={label}
              className={`group flex h-11 w-11 flex-col items-center justify-center rounded-md transition-colors ${
                view === id ? 'bg-copper/15 text-copper' : 'text-faint hover:text-nickel'
              }`}
            >
              <Icon size={18} strokeWidth={1.75} />
            </button>
          ))}
        </nav>
        <div className="text-faint" title="OSS-only модели">
          <CircleHelp size={16} />
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line px-6 py-3">
          <div>
            <div className="eyebrow">Горно-металлургический R&D · knowledge graph</div>
            <h1 className="font-display text-xl font-semibold tracking-tight">
              Научный клубок
            </h1>
          </div>
          <div className="flex items-center gap-4 text-xs">
            {stats.data && (
              <span className="chip text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-verified" />
                {stats.data.counts.nodes.toLocaleString('ru')} узлов ·{' '}
                {stats.data.counts.rels.toLocaleString('ru')} связей
              </span>
            )}
            <label className="flex items-center gap-2 text-muted">
              <span className="eyebrow">роль</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="rounded border border-line bg-surface px-2 py-1 font-mono text-xs text-ink"
              >
                {['researcher', 'analyst', 'project_manager', 'external_partner', 'curator'].map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-muted">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="accent-copper"
              />
              <span className="eyebrow">LLM-синтез</span>
            </label>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">
          {view === 'ask' && <AskView />}
          {view === 'coverage' && <CoverageView />}
          {view === 'glossary' && <GlossaryView />}
        </main>
      </div>

      <EvidenceDrawer />
    </div>
  );
}

function ClubokMark() {
  // A small tangle: three intertwined threads → the "клубок".
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.1" opacity="0.5" />
      <path d="M4 10c3-4 9-4 12 0M4 10c3 4 9 4 12 0M10 3v14" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}
