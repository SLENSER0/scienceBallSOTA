import { useQuery } from '@tanstack/react-query';
import {
  CircleHelp,
  LayoutGrid,
  Network,
  BookMarked,
  TriangleAlert,
  Columns3,
  MessagesSquare,
  LogOut,
  Library,
  Boxes,
  ClipboardList,
  ShieldCheck,
} from 'lucide-react';
import { api } from './api';
import { useStore, type View } from './store';
import { LoginView, useOidcCallback } from './components/LoginView';
import { ChatView } from './components/ChatView';
import { AskView } from './components/AskView';
import { LibraryView } from './components/LibraryView';
import { CompareView } from './components/CompareView';
import { CoverageView } from './components/CoverageView';
import { GapsView } from './components/GapsView';
import { GlossaryView } from './components/GlossaryView';
import { EntityDetailView } from './components/EntityDetailView';
import { CurationView } from './components/CurationView';
import { AdminView } from './components/AdminView';
import { EvidenceDrawer } from './components/EvidenceDrawer';

const NAV: { id: View; label: string; icon: typeof Network; roles?: string[] }[] = [
  { id: 'chat', label: 'Диалог', icon: MessagesSquare },
  { id: 'ask', label: 'Запрос', icon: Network },
  // Adding articles is a curator/researcher capability, not for external partners.
  { id: 'library', label: 'Библиотека', icon: Library, roles: ['researcher', 'analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'compare', label: 'Сравнение', icon: Columns3 },
  { id: 'coverage', label: 'Покрытие', icon: LayoutGrid },
  // External partners get a restricted view — no internal gap/risk analytics.
  { id: 'gaps', label: 'Пробелы и риски', icon: TriangleAlert, roles: ['researcher', 'analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'entities', label: 'Сущности', icon: Boxes },
  { id: 'glossary', label: 'Глоссарий', icon: BookMarked },
  // Curation + governance are internal-team surfaces.
  { id: 'curation', label: 'Курирование', icon: ClipboardList, roles: ['curator', 'project_manager', 'admin'] },
  { id: 'admin', label: 'Администрирование', icon: ShieldCheck, roles: ['curator', 'project_manager', 'admin'] },
];

export function App() {
  const { view, setView, role, useLlm, setUseLlm, user, signOut } = useStore();
  useOidcCallback();
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, enabled: !!user });

  // Gate the whole app on sign-in — «красивая авторизация» first.
  if (!user) return <LoginView />;

  const nav = NAV.filter((n) => !n.roles || n.roles.includes(role));
  if (!nav.some((n) => n.id === view)) setView('chat');

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left rail */}
      <aside className="flex w-16 shrink-0 flex-col items-center border-r border-line bg-graphite/60 py-4">
        <div className="mb-6 flex h-9 w-9 items-center justify-center rounded-md bg-copper/15 text-copper">
          <ClubokMark />
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {nav.map(({ id, label, icon: Icon }) => (
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
            <label className="flex cursor-pointer items-center gap-2 text-muted">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="accent-copper"
              />
              <span className="eyebrow">LLM-синтез</span>
            </label>
            {/* Signed-in identity + role + sign-out */}
            <div className="flex items-center gap-2 rounded-md border border-line bg-surface/60 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-verified" />
              <span className="text-ink">{user}</span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-copper">{role}</span>
              <button
                onClick={signOut}
                title="Выйти"
                className="ml-1 text-faint transition hover:text-contradiction"
              >
                <LogOut size={14} />
              </button>
            </div>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">
          {view === 'chat' && <ChatView />}
          {view === 'ask' && <AskView />}
          {view === 'library' && <LibraryView />}
          {view === 'compare' && <CompareView />}
          {view === 'coverage' && <CoverageView />}
          {view === 'gaps' && <GapsView />}
          {view === 'entities' && <EntityDetailView />}
          {view === 'glossary' && <GlossaryView />}
          {view === 'curation' && <CurationView />}
          {view === 'admin' && <AdminView />}
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
