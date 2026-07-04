import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { GitMerge, Layers, Loader2, ShieldAlert, Check } from 'lucide-react';
import { api } from '../api';
import type { ERCandidate, ERMention } from '../types';

// §8.8 — Экран ревью ER-кандидатов. Splink/decision-engine (§8.7) уже выдаёт
// группы слияния с match_probability и decision (auto_merge/review_needed/separate);
// здесь они становятся осязаемыми: каждая карточка показывает mentions группы,
// вероятность совпадения, решение и кнопку «Объединить», которая сливает остальные
// упоминания в canonical через POST /entities/merge (§8.9).

const STATUSES: { id: string; ru: string }[] = [
  { id: 'review_needed', ru: 'на ревью' },
  { id: 'auto_merge', ru: 'авто-слияние' },
  { id: 'separate', ru: 'раздельно' },
  { id: 'all', ru: 'все' },
];

const TYPES: { id: string; ru: string }[] = [
  { id: 'Material', ru: 'Материалы' },
  { id: 'Equipment', ru: 'Оборудование' },
  { id: 'Person', ru: 'Персоны' },
  { id: 'Lab', ru: 'Лаборатории' },
];

const DECISION: Record<string, { ru: string; cls: string }> = {
  auto_merge: { ru: 'авто-слияние', cls: 'text-verified border-verified/40' },
  review_needed: { ru: 'на ревью', cls: 'text-gap border-gap/40' },
  separate: { ru: 'раздельно', cls: 'text-faint border-line' },
};

function probColor(p: number): string {
  if (p >= 0.92) return 'bg-verified';
  if (p >= 0.7) return 'bg-gap';
  return 'bg-faint';
}

export function ERCandidatesView() {
  const [status, setStatus] = useState('review_needed');
  const [type, setType] = useState('Material');
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ['er-candidates', status, type],
    queryFn: () => api.erCandidates(status, type),
  });

  const candidates = q.data?.candidates ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Layers size={16} className="text-copper" /> Разрешение сущностей — кандидаты
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          группы слияния Splink · §8.8 · {q.data?.count ?? 0}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            {STATUSES.map((s) => (
              <button
                key={s.id}
                onClick={() => setStatus(s.id)}
                className={`chip ${status === s.id ? 'border-copper/50 text-copper' : 'text-faint'}`}
              >
                {s.ru}
              </button>
            ))}
          </div>
          <span className="mx-1 text-line">|</span>
          <div className="flex gap-1">
            {TYPES.map((t) => (
              <button
                key={t.id}
                onClick={() => setType(t.id)}
                className={`chip ${type === t.id ? 'border-copper/50 text-copper' : 'text-faint'}`}
              >
                {t.ru}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {q.isLoading ? (
          <div className="flex items-center gap-2 font-mono text-xs text-faint">
            <Loader2 size={14} className="animate-spin text-copper" /> прогон ER…
          </div>
        ) : q.isError ? (
          <div className="text-sm text-contradiction">Не удалось загрузить кандидатов.</div>
        ) : candidates.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <Layers size={30} className="mx-auto mb-2 text-faint" />
              <div className="font-mono text-xs text-faint">
                нет кандидатов «{STATUSES.find((s) => s.id === status)?.ru}» для этого типа
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto grid max-w-4xl gap-3">
            {candidates.map((c) => (
              <CandidateCard
                key={c.candidate_id}
                c={c}
                onMerged={() => qc.invalidateQueries({ queryKey: ['er-candidates'] })}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CandidateCard({ c, onMerged }: { c: ERCandidate; onMerged: () => void }) {
  const d = DECISION[c.decision] ?? DECISION.separate;
  const pct = Math.round(c.match_probability * 100);
  const drops = c.mentions.filter((m) => m.id !== c.canonical_id);

  const merge = useMutation({
    mutationFn: async () => {
      // Merge every non-canonical mention into the canonical representative (§8.9).
      for (const m of drops) {
        await api.mergeEntities(c.canonical_id, m.id, `ER merge · p=${c.match_probability}`);
      }
    },
    onSuccess: onMerged,
  });

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2">
        <span className={`chip ${d.cls}`}>{d.ru}</span>
        {c.blocked_by_review && (
          <span className="chip text-contradiction border-contradiction/40" title="в группе есть проверенный canonical — авто-слияние заблокировано (§8.9)">
            <ShieldAlert size={11} /> защищено
          </span>
        )}
        <span className="ml-auto font-mono text-[10px] text-faint">{c.candidate_id}</span>
      </div>

      {/* Probability meter */}
      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
          <div className={`h-full ${probColor(c.match_probability)}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="metric text-sm text-copper">{pct}%</span>
        <span className="font-mono text-[10px] text-faint">совпадение</span>
      </div>

      {/* Mentions */}
      <div className="mt-3 space-y-1">
        {c.mentions.map((m) => (
          <MentionRow key={m.id} m={m} canonical={m.id === c.canonical_id} />
        ))}
      </div>

      {/* Merge action */}
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => merge.mutate()}
          disabled={merge.isPending || merge.isSuccess || drops.length === 0}
          className="inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-1.5 text-xs text-copper transition hover:bg-copper/20 disabled:opacity-40"
        >
          {merge.isSuccess ? (
            <>
              <Check size={13} /> объединено
            </>
          ) : merge.isPending ? (
            <>
              <Loader2 size={13} className="animate-spin" /> слияние…
            </>
          ) : (
            <>
              <GitMerge size={13} /> Объединить ({drops.length})
            </>
          )}
        </button>
        {merge.isError && (
          <span className="font-mono text-[10px] text-contradiction">ошибка слияния</span>
        )}
        <span className="ml-auto font-mono text-[10px] text-faint">
          canonical → {c.canonical_id}
        </span>
      </div>
    </div>
  );
}

function MentionRow({ m, canonical }: { m: ERMention; canonical: boolean }) {
  return (
    <div
      className={`flex items-center gap-2 rounded px-2 py-1 text-xs ${
        canonical ? 'bg-copper/10' : 'bg-surface/50'
      }`}
    >
      <span className={canonical ? 'text-copper' : 'text-muted'}>{m.name ?? m.id}</span>
      {m.formula && <span className="font-mono text-[10px] text-faint">{m.formula}</span>}
      {canonical && (
        <span className="chip ml-1 text-copper border-copper/40 text-[9px]">canonical</span>
      )}
      {m.review_status && m.review_status !== 'pending' && (
        <span className="chip text-verified border-verified/40 text-[9px]">{m.review_status}</span>
      )}
      <span className="ml-auto font-mono text-[9px] text-faint">{m.id}</span>
    </div>
  );
}
