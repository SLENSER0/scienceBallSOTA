import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Crosshair, Layers, Loader2, Search, Sparkles, Target, Type } from 'lucide-react';

// §8.8 — query-time mention resolver: the resolve_mention cascade
//   exact alias → Neo4j fulltext (entity_name_index)
//               → vector search (entity_embedding_index) → Splink scoring
// Surfaces POST /api/v1/entities/resolve so a curator/researcher can type any
// surface form ("AA2024", a typo, a paraphrase) and see which canonical entity it
// grounds to, at what confidence, and *which tier decided* — plus the ranked
// alternatives with their per-tier evidence, exactly the disambiguation view the
// agent uses (§7.6). Self-contained fetch (reads the session token like api.ts) so
// it needs no edits to shared hub files.

interface CandidateScores {
  alias: number;
  fulltext: number;
  vector: number;
  splink: number;
}

interface ResolvedCandidate {
  entity_id: string;
  name: string | null;
  label: string | null;
  confidence: number;
  scores: CandidateScores;
}

interface EntityMention {
  text: string;
  canonical_id: string | null;
  entity_type: string | null;
  confidence: number;
  tier: string;
  name: string | null;
  candidates: ResolvedCandidate[];
}

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

async function postResolve(body: {
  text: string;
  entity_type: string | null;
}): Promise<EntityMention> {
  const res = await fetch('/api/v1/entities/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ ...body, limit: 6 }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<EntityMention>;
}

const TIER: Record<string, { ru: string; icon: typeof Type; cls: string }> = {
  alias: { ru: 'точный синоним', icon: Type, cls: 'text-verified border-verified/40' },
  fulltext: { ru: 'полнотекст', icon: Search, cls: 'text-copper border-copper/40' },
  vector: { ru: 'эмбеддинг', icon: Sparkles, cls: 'text-copper border-copper/40' },
  splink: { ru: 'Splink-скоринг', icon: Layers, cls: 'text-gap border-gap/40' },
  none: { ru: 'не найдено', icon: Crosshair, cls: 'text-contradiction border-contradiction/40' },
  empty: { ru: 'пусто', cls: 'text-faint border-line', icon: Crosshair },
};

const TYPES = ['', 'Material', 'Alloy', 'Equipment', 'Person', 'Lab', 'ResearchTeam'];

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const on = value > 0;
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-16 font-mono text-[9px] uppercase tracking-wide text-faint">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-surface/60">
        <div
          className={`h-full rounded ${on ? 'bg-copper' : ''}`}
          style={{ width: pct(Math.min(1, value)) }}
        />
      </div>
      <span className="w-9 text-right font-mono text-[9px] text-faint">
        {on ? value.toFixed(2) : '—'}
      </span>
    </div>
  );
}

export function MentionResolverView() {
  const [text, setText] = useState('AA2024');
  const [type, setType] = useState('');
  const resolve = useMutation({
    mutationFn: () => postResolve({ text: text.trim(), entity_type: type || null }),
  });

  const data = resolve.data;
  const submit = () => {
    if (text.trim()) resolve.mutate();
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col overflow-y-auto p-6">
      <header className="mb-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Target size={16} className="text-copper" /> Резолвер упоминаний
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-faint">
          каскад alias → полнотекст → эмбеддинг → Splink — привязка сырого текста к
          канонической сущности (§8.8)
        </div>
      </header>

      {/* Query form */}
      <div className="panel mb-4 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[220px]">
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-faint">
              упоминание
            </div>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
              placeholder="напр. AA2024, дюраль, Al-Cu…"
              className="w-full rounded border border-line bg-surface/60 px-2.5 py-1.5 text-sm text-ink outline-none focus:border-copper"
            />
          </label>
          <label>
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-faint">
              тип (опц.)
            </div>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="rounded border border-line bg-surface/60 px-2.5 py-1.5 text-sm text-ink outline-none focus:border-copper"
            >
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t || 'любой'}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={submit}
            disabled={!text.trim() || resolve.isPending}
            className="rounded bg-copper px-4 py-1.5 text-sm font-medium text-black disabled:opacity-50"
          >
            {resolve.isPending ? (
              <span className="flex items-center gap-1.5">
                <Loader2 size={14} className="animate-spin" /> резолв…
              </span>
            ) : (
              'Резолвить'
            )}
          </button>
        </div>
      </div>

      {resolve.isError && (
        <div className="mb-4 text-sm text-contradiction">Не удалось разрешить упоминание.</div>
      )}

      {data && (
        <>
          <BestMatch mention={data} />
          <CandidateList candidates={data.candidates} bestId={data.canonical_id} />
        </>
      )}
    </div>
  );
}

function BestMatch({ mention }: { mention: EntityMention }) {
  const tier = TIER[mention.tier] ?? TIER.none;
  const TierIcon = tier.icon;
  const matched = mention.canonical_id != null;
  return (
    <div className="panel mb-4 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wide text-faint">
          лучшее совпадение
        </div>
        <span className={`chip ${tier.cls}`}>
          <TierIcon size={11} /> {tier.ru}
        </span>
      </div>

      {matched ? (
        <div className="flex items-end gap-4">
          <div className="min-w-0">
            <div className="truncate text-lg text-ink">{mention.name ?? mention.canonical_id}</div>
            <div className="truncate font-mono text-[11px] text-faint">
              {mention.canonical_id}
              {mention.entity_type ? ` · ${mention.entity_type}` : ''}
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="metric text-3xl text-copper">{pct(mention.confidence)}</div>
            <div className="font-mono text-[10px] text-faint">уверенность</div>
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted">
          Ни один тир каскада не дал совпадения для «{mention.text}».
        </div>
      )}
    </div>
  );
}

function CandidateList({
  candidates,
  bestId,
}: {
  candidates: ResolvedCandidate[];
  bestId: string | null;
}) {
  if (candidates.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="font-mono text-[10px] uppercase tracking-wide text-faint">
        кандидаты ({candidates.length}) · вклад каждого тира
      </div>
      {candidates.map((c) => (
        <div
          key={c.entity_id}
          className={`panel p-3 ${c.entity_id === bestId ? 'border-copper/50' : ''}`}
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-sm text-ink/90">{c.name ?? c.entity_id}</div>
              <div className="truncate font-mono text-[10px] text-faint">
                {c.entity_id}
                {c.label ? ` · ${c.label}` : ''}
              </div>
            </div>
            <span className="chip text-copper border-copper/40 shrink-0">{pct(c.confidence)}</span>
          </div>
          <div className="space-y-1">
            <ScoreBar label="alias" value={c.scores.alias} />
            <ScoreBar label="fulltext" value={c.scores.fulltext} />
            <ScoreBar label="vector" value={c.scores.vector} />
            <ScoreBar label="splink" value={c.scores.splink} />
          </div>
        </div>
      ))}
    </div>
  );
}
