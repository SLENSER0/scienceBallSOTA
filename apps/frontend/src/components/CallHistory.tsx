import { History, Trash2, X } from 'lucide-react';
import { useCallHistory, type CallEntry } from '../lib/callHistory';

// Reusable «история вызовов» panel — shows a feature's previous calls (queries / agent
// runs) newest-first; clicking one replays it via onPick. Backed by localStorage.

function ago(ts: number): string {
  const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return 'только что';
  if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
  if (s < 86400) return `${Math.floor(s / 3600)} ч назад`;
  return `${Math.floor(s / 86400)} дн назад`;
}

export function CallHistory({
  feature,
  onPick,
  title = 'История запросов',
  max = 8,
}: {
  feature: string;
  onPick: (entry: CallEntry) => void;
  title?: string;
  max?: number;
}) {
  const { entries, remove, clear } = useCallHistory(feature);
  if (entries.length === 0) return null;

  return (
    <div className="panel mt-4 p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <History size={13} className="text-copper" />
        <span className="eyebrow">{title}</span>
        <button
          onClick={clear}
          className="ml-auto flex items-center gap-1 font-mono text-[10px] text-faint transition hover:text-contradiction"
          title="Очистить историю"
        >
          <Trash2 size={11} /> очистить
        </button>
      </div>
      <ul className="space-y-1">
        {entries.slice(0, max).map((e) => (
          <li key={e.id} className="group flex items-center gap-2">
            <button
              onClick={() => onPick(e)}
              className="min-w-0 flex-1 truncate rounded px-2 py-1 text-left text-[13px] text-muted transition hover:bg-surface/60 hover:text-copper"
              title={e.label}
            >
              {e.label}
            </button>
            <span className="shrink-0 font-mono text-[9px] text-faint">{ago(e.ts)}</span>
            <button
              onClick={() => remove(e.id)}
              className="shrink-0 text-faint opacity-0 transition group-hover:opacity-100 hover:text-contradiction"
              title="Удалить"
            >
              <X size={12} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
