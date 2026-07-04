import { useCallback, useEffect, useState } from 'react';

// Per-feature history of previous calls (queries / agent runs), kept in localStorage so
// it survives reloads and tab switches. Each feature (advisor, ask, contradictions, …)
// gets its own ring buffer; clicking an entry re-runs it. Honest & local — no server.

export interface CallEntry {
  id: string;
  label: string; // what to show (the query / target)
  ts: number; // epoch ms
  payload?: Record<string, unknown>; // enough to replay the call
}

const KEY = (feature: string) => `sb.history.${feature}`;
const MAX = 25;

function read(feature: string): CallEntry[] {
  try {
    const raw = localStorage.getItem(KEY(feature));
    return raw ? (JSON.parse(raw) as CallEntry[]) : [];
  } catch {
    return [];
  }
}

function write(feature: string, entries: CallEntry[]) {
  try {
    localStorage.setItem(KEY(feature), JSON.stringify(entries.slice(0, MAX)));
    // notify same-tab listeners (storage event only fires cross-tab)
    window.dispatchEvent(new CustomEvent('sb-history', { detail: feature }));
  } catch {
    /* quota / private mode — history is best-effort */
  }
}

/** Record a call. Dedups by label (moves an existing identical call to the top). */
export function pushCall(feature: string, label: string, payload?: Record<string, unknown>) {
  const trimmed = label.trim();
  if (!trimmed) return;
  const prev = read(feature).filter((e) => e.label !== trimmed);
  const entry: CallEntry = {
    id: `${Date.now()}-${Math.floor(performance.now())}`,
    label: trimmed,
    ts: Date.now(),
    payload,
  };
  write(feature, [entry, ...prev]);
}

/** React hook: live list of a feature's history + helpers. */
export function useCallHistory(feature: string) {
  const [entries, setEntries] = useState<CallEntry[]>(() => read(feature));

  useEffect(() => {
    const refresh = (e: Event) => {
      if (e instanceof CustomEvent && e.detail && e.detail !== feature) return;
      setEntries(read(feature));
    };
    window.addEventListener('sb-history', refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener('sb-history', refresh);
      window.removeEventListener('storage', refresh);
    };
  }, [feature]);

  const remove = useCallback(
    (id: string) => write(feature, read(feature).filter((e) => e.id !== id)),
    [feature],
  );
  const clear = useCallback(() => write(feature, []), [feature]);
  return { entries, remove, clear };
}
