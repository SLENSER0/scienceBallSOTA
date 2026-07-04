import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Gavel, Loader2, ShieldCheck, Sparkles } from 'lucide-react';

// §16.6 «Замкнуть контур»: human-in-the-loop superstructure over the read-only arbiter.
// The arbiter (ContradictionsView) reasons and returns a verdict; this panel lets the
// curator COMMIT it — accept the likely-correct side → the Contradiction flips to
// `resolved`, losing CONTRADICTS edges are quenched, and a CurationEvent is recorded.
// Standalone (own fetch helpers) so it does not depend on edits to api.ts.

const PRACTICE: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};

function authHeaders(): Record<string, string> {
  try {
    const raw = localStorage.getItem('sb.session');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.token) return { Authorization: `Bearer ${s.token}` };
      if (s?.role) return { 'X-Role': s.role };
    }
  } catch {
    /* ignore */
  }
  return {};
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface ResolveCandidate {
  claim_id: string;
  value: number | null;
  unit: string | null;
  property: string | null;
  practice: string | null;
  year: number | null;
  country: string | null;
  confidence: number | null;
  evidence: string | null;
  evidence_count: number;
  support: number;
  likely_correct: boolean;
}

interface CandidatesResponse {
  id: string;
  name: string;
  status: string | null;
  resolution: string | null;
  candidates: ResolveCandidate[];
  likely_correct_id: string | null;
}

interface ResolveResponse {
  event: { event_id: string; action: string; target_id: string };
  winner_claim_id: string;
  loser_claim_ids: string[];
  quenched_edges: number;
  status: string;
  resolution: string;
}

const arbiterApi = {
  candidates: (cid: string): Promise<CandidatesResponse> =>
    req(`/api/v1/arbiter/${encodeURIComponent(cid)}/candidates`),
  resolve: (cid: string, winner_claim_id: string | null, reason: string): Promise<ResolveResponse> =>
    req(`/api/v1/arbiter/${encodeURIComponent(cid)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ winner_claim_id, reason }),
    }),
};

export function ArbiterResolvePanel({ cid }: { cid: string }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const cands = useQuery({
    queryKey: ['arbiter-candidates', cid],
    queryFn: () => arbiterApi.candidates(cid),
  });

  const resolve = useMutation({
    mutationFn: (winner: string | null) => arbiterApi.resolve(cid, winner, reason),
    onSuccess: () => {
      cands.refetch();
      // refresh the contradictions list so the resolved item shows its new status
      qc.invalidateQueries({ queryKey: ['contradictions'] });
    },
  });

  const data = cands.data;
  const alreadyResolved = data?.status === 'resolved';
  const likelyId = data?.likely_correct_id ?? null;
  const list = useMemo(() => data?.candidates ?? [], [data]);
  const done = resolve.data;

  if (cands.isLoading) {
    return (
      <div className="mt-4 flex items-center gap-2 font-mono text-[11px] text-faint">
        <Loader2 size={13} className="animate-spin text-copper" /> загрузка сторон…
      </div>
    );
  }
  if (!data || list.length < 1) return null;

  return (
    <div className="mt-6 rounded-md border border-line bg-graphite/40 p-4">
      <div className="flex items-center gap-2">
        <Gavel size={15} className="text-copper" />
        <div className="text-sm text-nickel">Разрешить противоречие</div>
        <div className="ml-auto font-mono text-[10px] text-faint">
          человек-в-контуре · CurationEvent
        </div>
      </div>

      {alreadyResolved ? (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-verified/40 bg-verified/5 px-3 py-2 text-sm text-verified">
          <ShieldCheck size={14} />
          разрешено · победившая сторона{' '}
          <code className="font-mono text-[11px] text-verified/90">{data.resolution}</code>
        </div>
      ) : done ? (
        <div className="mt-3 rounded-md border border-verified/40 bg-verified/5 px-3 py-2 text-sm text-verified">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} /> противоречие разрешено
          </div>
          <div className="mt-1 font-mono text-[10px] text-faint">
            CurationEvent {done.event.event_id.slice(0, 12)}… · погашено рёбер:{' '}
            {done.quenched_edges}
          </div>
        </div>
      ) : (
        <>
          <p className="mt-2 text-[12px] leading-snug text-muted">
            Выберите сторону, которую вносим в граф как верную. Узел получит{' '}
            <span className="text-verified">status=resolved</span>, конфликтующие рёбра будут
            погашены, действие фиксируется как <span className="text-copper">CurationEvent</span>.
          </p>

          <div className="mt-3 space-y-2">
            {list.map((c) => (
              <div
                key={c.claim_id}
                className={`rounded-md border p-3 ${
                  c.likely_correct ? 'border-copper/40 bg-copper/5' : 'border-line bg-surface/40'
                }`}
              >
                <div className="flex items-baseline gap-2">
                  <span className="metric text-lg text-copper">
                    {c.value ?? '—'}
                    <span className="ml-1 text-xs text-faint">{c.unit ?? ''}</span>
                  </span>
                  {c.likely_correct && (
                    <span className="chip text-copper border-copper/40">
                      <Sparkles size={11} className="mr-1" /> вероятно верно
                    </span>
                  )}
                  <span className="ml-auto font-mono text-[10px] text-faint">
                    поддержка {c.support.toFixed(2)} · ссылок {c.evidence_count}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {c.property && <span className="chip text-faint">{c.property}</span>}
                  {c.practice && (
                    <span className="chip text-faint">{PRACTICE[c.practice] ?? c.practice}</span>
                  )}
                  {c.year && <span className="chip text-faint">{c.year}</span>}
                  {c.country && <span className="chip text-faint">{c.country}</span>}
                </div>
                {c.evidence && (
                  <div className="mt-2 line-clamp-3 text-[12px] leading-snug text-muted">
                    «{c.evidence}»
                  </div>
                )}
                <div className="mt-2 flex justify-end">
                  <button
                    onClick={() => resolve.mutate(c.claim_id)}
                    disabled={resolve.isPending}
                    className="rounded border border-line px-2.5 py-1 font-mono text-[11px] text-muted transition hover:border-copper/50 hover:text-copper disabled:opacity-50"
                  >
                    принять эту сторону
                  </button>
                </div>
              </div>
            ))}
          </div>

          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="причина решения (опционально) — попадёт в CurationEvent"
            className="mt-3 w-full rounded border border-line bg-surface/60 px-2.5 py-1.5 text-xs text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
          />

          <button
            onClick={() => resolve.mutate(likelyId)}
            disabled={resolve.isPending || !likelyId}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-md bg-copper/90 px-3 py-2 text-sm font-medium text-graphite transition hover:bg-copper disabled:opacity-50"
          >
            {resolve.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <ShieldCheck size={14} />
            )}
            принять likely-correct сторону
          </button>

          {resolve.isError && (
            <div className="mt-2 text-[12px] text-contradiction">
              Не удалось разрешить: {(resolve.error as Error).message}
            </div>
          )}
        </>
      )}
    </div>
  );
}
