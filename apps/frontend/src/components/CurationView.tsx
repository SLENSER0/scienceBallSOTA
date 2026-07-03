import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ClipboardList, Clock, History, Loader2, X } from 'lucide-react';
import { api } from '../api';

// Экран Admin / Curation (§17.15 / §5.2.8): the review queue of low-confidence
// entities, gaps and contradictions, with approve/reject actions and per-entity
// change history. Writes go through the RBAC-gated /entities/{id}/status endpoint.

const STATUS_STYLE: Record<string, string> = {
  pending: 'text-gap border-gap/40',
  approved: 'text-verified border-verified/40',
  rejected: 'text-contradiction border-contradiction/40',
  reviewed: 'text-copper border-copper/40',
};

export function CurationView() {
  const qc = useQueryClient();
  const queue = useQuery({ queryKey: ['curation-queue'], queryFn: api.reviewQueue });
  const [openId, setOpenId] = useState<string | null>(null);

  const act = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.setEntityStatus(id, status, 'via curation queue'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['curation-queue'] }),
  });

  const items = queue.data?.items ?? [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">Курирование · очередь ревью</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <ClipboardList size={22} className="text-copper" /> Очередь на проверку
        </h1>
        <p className="mt-1 text-sm text-faint">
          Сущности, пробелы и противоречия с низкой достоверностью или статусом «на ревью».
          Утвердите или отклоните — решение попадёт в историю изменений (§12).
        </p>

        {queue.isLoading && (
          <div className="mt-8 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> загрузка очереди…
          </div>
        )}

        <div className="mt-5 space-y-2">
          {items.map((it) => (
            <div key={it.id} className="panel p-3">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="chip text-faint">{it.label}</span>
                    <span
                      className={`chip ${STATUS_STYLE[it.review_status] ?? 'text-faint border-line'}`}
                    >
                      {it.review_status}
                    </span>
                    {typeof it.confidence === 'number' && (
                      <span className="font-mono text-[10px] text-faint">
                        conf {Math.round(it.confidence * 100)}%
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-sm text-ink">{it.name}</div>
                  <div className="mt-0.5 font-mono text-[10px] text-faint">{it.id}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => act.mutate({ id: it.id, status: 'approved' })}
                    disabled={act.isPending}
                    className="chip text-verified hover:border-verified/50 disabled:opacity-40"
                    title="Утвердить"
                  >
                    <Check size={12} /> Утвердить
                  </button>
                  <button
                    onClick={() => act.mutate({ id: it.id, status: 'rejected' })}
                    disabled={act.isPending}
                    className="chip text-contradiction hover:border-contradiction/50 disabled:opacity-40"
                    title="Отклонить"
                  >
                    <X size={12} /> Отклонить
                  </button>
                  <button
                    onClick={() => setOpenId(openId === it.id ? null : it.id)}
                    className="chip text-faint hover:border-copper/40 hover:text-copper"
                    title="История"
                  >
                    <History size={12} />
                  </button>
                </div>
              </div>
              {openId === it.id && <HistoryPanel id={it.id} />}
            </div>
          ))}
          {!queue.isLoading && items.length === 0 && (
            <div className="panel py-10 text-center font-mono text-[11px] text-faint">
              очередь пуста — всё проверено
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HistoryPanel({ id }: { id: string }) {
  const hist = useQuery({ queryKey: ['entity-history', id], queryFn: () => api.entityHistory(id) });
  const rows = hist.data?.history ?? [];
  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
        <Clock size={11} /> история изменений
      </div>
      {hist.isLoading ? (
        <div className="font-mono text-[11px] text-faint">загрузка…</div>
      ) : rows.length ? (
        <ul className="space-y-1">
          {rows.map((r, i) => (
            <li key={i} className="font-mono text-[11px] text-muted">
              {JSON.stringify(r)}
            </li>
          ))}
        </ul>
      ) : (
        <div className="font-mono text-[11px] text-faint">нет записей</div>
      )}
    </div>
  );
}
