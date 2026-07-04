import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowRight,
  Check,
  GitMerge,
  History,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Undo2,
} from 'lucide-react';
import { api } from '../api';

// §8.9 — Undo merge + обратимость (merged_from) в UI курирования.
// Reversibility уже есть в бэкенде: каждое слияние сущностей пишет
// CurationEvent{action:merge} со снимком `before` поглощённого узла — это и есть
// обратная ссылка merged_from. Здесь куратор видит журнал слияний и может одной
// кнопкой «Откатить слияние»: бэкенд воссоздаёт исходную сущность из снимка и
// пишет компенсирующее CurationEvent{action:split} (ничего не удаляется). Экран
// делает безопасность операций куратора осязаемой.

interface MergeRecord {
  event_id: string;
  actor: string | null;
  reason: string | null;
  created_at: string | null;
  keep_id: string | null;
  keep_name: string | null;
  keep_label: string | null;
  keep_exists: boolean;
  dropped_id: string | null;
  dropped_name: string | null;
  dropped_label: string | null;
  undone: boolean;
  undone_by: string | null;
  undone_at: string | null;
  reversible: boolean;
  blocked_reason: string | null;
}

interface MergesResponse {
  count: number;
  items: MergeRecord[];
}

const FILTERS: { id: string; ru: string }[] = [
  { id: 'reversible', ru: 'обратимые' },
  { id: 'undone', ru: 'откачены' },
  { id: 'all', ru: 'все' },
];

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function MergeUndoView() {
  const [filter, setFilter] = useState('reversible');
  const qc = useQueryClient();

  const q = useQuery<MergesResponse>({
    queryKey: ['curation-merges'],
    queryFn: () => api.mergeHistory(100) as unknown as Promise<MergesResponse>,
  });

  const all = q.data?.items ?? [];
  const items = useMemo(() => {
    if (filter === 'reversible') return all.filter((m) => m.reversible);
    if (filter === 'undone') return all.filter((m) => m.undone);
    return all;
  }, [all, filter]);

  const reversibleCount = all.filter((m) => m.reversible).length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Undo2 size={16} className="text-copper" /> Откат ошибочных слияний
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          можно откатить: {reversibleCount} из {all.length}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={`chip ${filter === f.id ? 'border-copper/50 text-copper' : 'text-faint'}`}
              >
                {f.ru}
              </button>
            ))}
          </div>
          <span className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] text-faint">
            <ShieldCheck size={11} className="text-verified" /> ничего не удаляется безвозвратно
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {q.isLoading ? (
          <div className="flex items-center gap-2 font-mono text-xs text-faint">
            <Loader2 size={14} className="animate-spin text-copper" /> загрузка журнала слияний…
          </div>
        ) : q.isError ? (
          <div className="text-sm text-contradiction">Не удалось загрузить журнал слияний.</div>
        ) : items.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <History size={30} className="mx-auto mb-2 text-faint" />
              <div className="font-mono text-xs text-faint">
                нет записей «{FILTERS.find((f) => f.id === filter)?.ru}»
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto grid max-w-4xl gap-3">
            {items.map((m) => (
              <MergeCard
                key={m.event_id}
                m={m}
                onUndone={() => qc.invalidateQueries({ queryKey: ['curation-merges'] })}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MergeCard({ m, onUndone }: { m: MergeRecord; onUndone: () => void }) {
  const undo = useMutation({
    mutationFn: () => api.undoMerge(m.event_id, 'откат слияния куратором'),
    onSuccess: onUndone,
  });

  const done = m.undone || undo.isSuccess;

  return (
    <div className={`panel p-4 ${done ? 'opacity-70' : ''}`}>
      <div className="flex items-center gap-2">
        {done ? (
          <span className="chip border-verified/40 text-verified">
            <RotateCcw size={11} /> откачено
          </span>
        ) : m.reversible ? (
          <span className="chip border-copper/40 text-copper">
            <Undo2 size={11} /> обратимо
          </span>
        ) : (
          <span
            className="chip border-line text-faint"
            title={m.blocked_reason ?? 'снимок недоступен'}
          >
            необратимо
          </span>
        )}
        {m.keep_label && (
          <span className="chip border-line text-faint">{m.keep_label}</span>
        )}
        <span className="ml-auto font-mono text-[10px] text-faint">{fmtTime(m.created_at)}</span>
      </div>

      {/* merge visualization: dropped → keep */}
      <div className="mt-3 flex items-center gap-2 text-xs">
        <div className="min-w-0 flex-1 rounded bg-surface/50 px-2 py-1.5">
          <div className="truncate text-nickel" title={m.dropped_id ?? ''}>
            {m.dropped_name ?? m.dropped_id ?? '—'}
          </div>
          <div className="truncate font-mono text-[10px] text-faint">
            {m.dropped_id ?? 'снимок отсутствует'}
          </div>
        </div>
        <GitMerge size={14} className="shrink-0 text-copper" />
        <ArrowRight size={12} className="shrink-0 text-faint" />
        <div className="min-w-0 flex-1 rounded bg-copper/10 px-2 py-1.5">
          <div className="truncate text-nickel" title={m.keep_id ?? ''}>
            {m.keep_name ?? m.keep_id ?? '—'}
          </div>
          <div className="truncate font-mono text-[10px] text-faint">
            {m.keep_id ?? '—'}
            {!m.keep_exists && m.keep_id ? ' · целевой узел отсутствует' : ''}
          </div>
        </div>
      </div>

      {m.reason && (
        <div className="mt-2 text-[11px] text-faint">
          <span className="text-nickel">причина:</span> {m.reason}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => undo.mutate()}
          disabled={done || !m.reversible || undo.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-1.5 text-xs text-copper transition hover:bg-copper/20 disabled:opacity-40"
        >
          {done ? (
            <>
              <Check size={13} /> восстановлено
            </>
          ) : undo.isPending ? (
            <>
              <Loader2 size={13} className="animate-spin" /> откат…
            </>
          ) : (
            <>
              <Undo2 size={13} /> Откатить слияние
            </>
          )}
        </button>
        {undo.isError && (
          <span className="font-mono text-[10px] text-contradiction">
            {(undo.error as Error)?.message ?? 'ошибка отката'}
          </span>
        )}
        <span className="ml-auto font-mono text-[10px] text-faint">
          {m.actor ?? 'curator'}
          {done && m.undone_by ? ` · откат: ${m.undone_by}` : ''}
        </span>
      </div>
    </div>
  );
}
