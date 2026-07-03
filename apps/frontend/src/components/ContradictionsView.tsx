import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { GitCompareArrows, Loader2, Scale, Sparkles } from 'lucide-react';
import { api } from '../api';
import type { ContradictionAnalysis, ContradictionSide } from '../types';

// Agentic contradiction arbiter — «где наука спорит». The left column lists flagged
// conflicts (same property, different values) ranked by spread; picking one runs an
// arbiter agent (GLM-5.2) that reasons from each side's provenance (geography, vintage,
// evidence) whether it's a genuine conflict or explained by differing conditions.

const VERDICT: Record<string, { ru: string; cls: string }> = {
  genuine: { ru: 'настоящий конфликт', cls: 'text-contradiction border-contradiction/40' },
  context_dependent: { ru: 'зависит от условий', cls: 'text-gap border-gap/40' },
  resolved: { ru: 'разрешимо', cls: 'text-verified border-verified/40' },
  insufficient: { ru: 'мало данных', cls: 'text-faint border-line' },
};

const PRACTICE: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};

export function ContradictionsView() {
  const list = useQuery({ queryKey: ['contradictions'], queryFn: () => api.contradictionsList(50) });
  const [sel, setSel] = useState<string | null>(null);

  const analyze = useMutation({
    mutationFn: (cid: string) => api.analyzeContradiction(cid),
  });

  const items = list.data?.contradictions ?? [];

  const pick = (cid: string) => {
    setSel(cid);
    analyze.mutate(cid);
  };

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[320px_1fr]">
      {/* Left: list */}
      <aside className="flex min-h-0 flex-col border-r border-line bg-graphite/40">
        <div className="border-b border-line px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-nickel">
            <GitCompareArrows size={15} className="text-copper" /> Противоречия
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-faint">
            где источники расходятся · {items.length}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {list.isLoading ? (
            <div className="flex items-center gap-2 p-3 font-mono text-[11px] text-faint">
              <Loader2 size={13} className="animate-spin text-copper" /> загрузка…
            </div>
          ) : (
            items.map((c) => (
              <button
                key={c.id}
                onClick={() => pick(c.id)}
                className={`mb-1 w-full rounded px-2.5 py-2 text-left transition ${
                  sel === c.id ? 'bg-copper/15' : 'hover:bg-surface/60'
                }`}
              >
                <div className={`text-xs ${sel === c.id ? 'text-copper' : 'text-muted'}`}>
                  {c.name}
                </div>
                {c.values.length >= 2 && (
                  <div className="mt-0.5 font-mono text-[10px] text-faint">
                    {Math.min(...c.values)}…{Math.max(...c.values)} {c.unit ?? ''}
                    {c.material ? ` · ${c.material}` : ''}
                  </div>
                )}
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Right: arbitration */}
      <section className="min-h-0 overflow-y-auto p-6">
        {!sel ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <Scale size={30} className="mx-auto mb-2 text-faint" />
              <div className="font-mono text-xs text-faint">
                выберите противоречие — агент-арбитр вынесет вердикт
              </div>
            </div>
          </div>
        ) : analyze.isPending ? (
          <div className="flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> агент-арбитр анализирует
            стороны…
          </div>
        ) : analyze.data ? (
          <Arbitration a={analyze.data} />
        ) : analyze.isError ? (
          <div className="text-sm text-contradiction">Не удалось проанализировать.</div>
        ) : null}
      </section>
    </div>
  );
}

function Arbitration({ a }: { a: ContradictionAnalysis }) {
  const v = VERDICT[a.verdict] ?? VERDICT.insufficient;
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-display text-lg font-semibold tracking-tight">{a.name}</h1>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className={`chip ${v.cls}`}>
          <Scale size={12} /> {v.ru}
        </span>
        {a.model && (
          <span className="font-mono text-[10px] text-faint" title="агент-арбитр">
            <Sparkles size={10} className="mr-1 inline" />
            {a.model}
          </span>
        )}
      </div>

      {a.explanation && (
        <div className="panel mt-3 p-4 text-sm text-ink/90">{a.explanation}</div>
      )}

      {/* Sides side-by-side */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {a.sides.slice(0, 4).map((s, i) => (
          <SideCard key={i} s={s} idx={i} />
        ))}
      </div>

      {a.recommendation && (
        <div className="mt-4 rounded-md border border-copper/30 bg-copper/5 p-4">
          <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-copper">
            рекомендация
          </div>
          <div className="text-sm text-ink/90">{a.recommendation}</div>
        </div>
      )}
    </div>
  );
}

function SideCard({ s, idx }: { s: ContradictionSide; idx: number }) {
  const label = String.fromCharCode(65 + idx); // A, B, C…
  return (
    <div className="panel p-3">
      <div className="flex items-baseline gap-2">
        <span className="metric text-lg text-copper">
          {s.value}
          <span className="ml-1 text-xs text-faint">{s.unit ?? ''}</span>
        </span>
        <span className="ml-auto font-mono text-[10px] text-faint">источник {label}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {s.practice && <span className="chip text-faint">{PRACTICE[s.practice] ?? s.practice}</span>}
        {s.year && <span className="chip text-faint">{s.year}</span>}
        {s.country && <span className="chip text-faint">{s.country}</span>}
      </div>
      {s.evidence && (
        <div className="mt-2 line-clamp-4 text-[12px] leading-snug text-muted">«{s.evidence}»</div>
      )}
    </div>
  );
}
