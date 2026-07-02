import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ClipboardList, SearchX } from 'lucide-react';
import { api } from '../api';

export function GapsView() {
  const gaps = useQuery({ queryKey: ['gaps'], queryFn: api.gaps });
  const contradictions = useQuery({ queryKey: ['contradictions'], queryFn: api.contradictions });
  const queue = useQuery({ queryKey: ['queue'], queryFn: api.reviewQueue });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">зоны риска · верификация знаний</div>
        <h2 className="mb-5 font-display text-2xl font-semibold">Пробелы, противоречия и очередь ревью</h2>

        <div className="grid gap-4 lg:grid-cols-3">
          <Panel
            icon={<SearchX size={15} />}
            tone="gap"
            title="Пробелы в знаниях"
            count={gaps.data?.count ?? 0}
          >
            {gaps.data?.gaps.map((g) => (
              <li key={g.id} className="text-ink/85">
                {g.name}
                {g.type && <span className="ml-1 font-mono text-[10px] text-faint">[{g.type}]</span>}
              </li>
            ))}
          </Panel>

          <Panel
            icon={<AlertTriangle size={15} />}
            tone="contradiction"
            title="Противоречия"
            count={contradictions.data?.count ?? 0}
          >
            {contradictions.data?.contradictions.map((c) => (
              <li key={c.id} className="text-ink/85">
                {c.name}
              </li>
            ))}
          </Panel>

          <Panel
            icon={<ClipboardList size={15} />}
            tone="nickel"
            title="Очередь ревью"
            count={queue.data?.items.length ?? 0}
          >
            {queue.data?.items.map((it) => (
              <li key={it.id} className="text-ink/85">
                <span className="font-mono text-[10px] text-faint">{it.label}</span> {it.name}
                {it.confidence != null && (
                  <span className="ml-1 metric text-[10px] text-faint">
                    conf {Math.round(it.confidence * 100)}%
                  </span>
                )}
              </li>
            ))}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Panel({
  icon,
  tone,
  title,
  count,
  children,
}: {
  icon: React.ReactNode;
  tone: 'gap' | 'contradiction' | 'nickel';
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  const color =
    tone === 'gap' ? 'text-gap' : tone === 'contradiction' ? 'text-contradiction' : 'text-nickel';
  return (
    <div className="panel p-4">
      <div className={`mb-3 flex items-center gap-2 font-mono text-xs uppercase tracking-wide ${color}`}>
        {icon}
        {title}
        <span className="ml-auto metric text-base text-ink">{count}</span>
      </div>
      <ul className="space-y-1.5 text-sm">{children}</ul>
    </div>
  );
}
