import { useState, type ReactNode } from 'react';

// Generic tabbed hub — collapses several sibling screens into one sidebar entry with
// tabs. Only the active tab's component mounts (lazy render), so heavy views don't all
// load at once. Children keep their own h-full/scroll (the app hosts views in an
// overflow-hidden <main>), so the body just gives them a bounded flex area.

export interface HubTab {
  id: string;
  label: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  render: () => ReactNode;
}

export function TabHub({ eyebrow, tabs }: { eyebrow: string; tabs: HubTab[] }) {
  const [active, setActive] = useState(tabs[0]?.id);
  const cur = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line px-6 pt-4">
        <div className="eyebrow mb-2">{eyebrow}</div>
        <div className="flex flex-wrap gap-1">
          {tabs.map((t) => {
            const Icon = t.icon;
            const on = active === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActive(t.id)}
                className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
                  on ? 'border-copper text-copper' : 'border-transparent text-faint hover:text-ink'
                }`}
              >
                {Icon && <Icon size={14} />} {t.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="min-h-0 flex-1">{cur.render()}</div>
    </div>
  );
}
