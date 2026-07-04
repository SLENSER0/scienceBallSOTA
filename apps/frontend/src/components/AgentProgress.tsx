import { CheckCircle2, Loader2 } from 'lucide-react';

// Honest agent-fan-out progress bar. The fill is ALWAYS done/total — it advances only
// when a real agent finishes (driven by SSE completion events), never by a timer or an
// animation. When total is unknown yet (0) it shows an indeterminate "запускаем агентов…"
// state rather than a fake percentage.
export function AgentProgress({
  done,
  total,
  running,
  label = 'готово',
}: {
  done: number;
  total: number;
  running: boolean;
  label?: string;
}) {
  const known = total > 0;
  const pct = known ? Math.round((done / total) * 100) : 0;
  return (
    <div className="panel p-3">
      <div className="mb-1.5 flex items-center gap-2 text-xs">
        {running ? (
          <Loader2 size={13} className="animate-spin text-copper" />
        ) : (
          <CheckCircle2 size={13} className="text-verified" />
        )}
        <span className="text-nickel">
          {known ? (
            <>
              <span className="metric text-copper">{done}</span>
              <span className="text-faint"> / {total}</span> {label}
            </>
          ) : (
            'запускаем агентов…'
          )}
        </span>
        {known && <span className="ml-auto font-mono text-[10px] text-faint">{pct}%</span>}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
        {known ? (
          <div
            className="h-full rounded-full bg-copper transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        ) : (
          // indeterminate: unknown total → a subtle moving stripe, not a fake %.
          <div className="h-full w-1/3 animate-pulse rounded-full bg-copper/50" />
        )}
      </div>
    </div>
  );
}
