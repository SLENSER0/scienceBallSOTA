import { api } from '../api';
import { useStore } from '../store';
import type { PrioritizedGap } from '../types';

// Singleton owner of the gap-prioritization SSE stream. Living OUTSIDE React means the
// stream (and its results) survive component unmount: navigating away from «Карта
// пробелов» no longer kills the agents, and navigating back re-reads the cached cards
// from the store instead of restarting the whole run. Only a manual refresh re-streams.

let es: EventSource | null = null;

function rankGaps(gs: PrioritizedGap[]): PrioritizedGap[] {
  // Scored first (by priority), unscored last — mirrors the backend ranking.
  return [...gs].sort((a, b) => Number(b.scored) - Number(a.scored) || b.priority - a.priority);
}

/**
 * Ensure the gap-map stream has run. Cheap no-op if it is already running or done —
 * that is exactly the cache: a second visit finds phase !== 'idle' and returns instantly.
 * Pass force=true (refresh button) to tear down and re-stream from scratch.
 */
export function startGapMap(force = false): void {
  const { gapMap, setGapMap } = useStore.getState();
  if (!force && gapMap.phase !== 'idle') return; // cached — running or done
  if (es) {
    es.close();
    es = null;
  }
  setGapMap({ phase: 'running', gaps: [], done: 0, total: 0 });

  const source = new EventSource(api.gapsPrioritizedStreamUrl(14));
  es = source;

  source.addEventListener('start', (e) => {
    useStore.getState().setGapMap({ total: JSON.parse((e as MessageEvent).data).total ?? 0 });
  });
  source.addEventListener('gap', (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    const prev = useStore.getState().gapMap.gaps;
    useStore.getState().setGapMap({
      done: d.done ?? 0,
      gaps: rankGaps([...prev, d.gap as PrioritizedGap]),
    });
  });
  const finish = () => {
    useStore.getState().setGapMap({ phase: 'done' });
    source.close();
    if (es === source) es = null;
  };
  source.addEventListener('done', finish);
  source.addEventListener('error', finish);
}
