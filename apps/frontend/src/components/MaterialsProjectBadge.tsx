import { useQuery } from '@tanstack/react-query';
import { BadgeCheck, ExternalLink } from 'lucide-react';
import { api } from '../api';

// Бейдж авторитета Materials Project (§8.2 / §17.11): показывает «✓ Materials Project
// mp-XXXX» + каноническую формулу на экране Entity Detail, когда сущность (сплав/материал)
// сшита с записью Materials Project. Мгновенное доказательство канонизации против внешнего
// авторитета. Данные берёт из /api/v1/entities/{id}/materials-project (crosswalk уже записан
// в attributes / ExternalRef). Если привязки нет — рендерит null (бейдж скрыт).

export function MaterialsProjectBadge({ entityId }: { entityId: string }) {
  const q = useQuery({
    queryKey: ['mp-authority', entityId],
    queryFn: () => api.materialsProjectBadge(entityId),
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000,
  });

  const b = q.data;
  if (!b || !b.has_authority || !b.mp_id) return null;

  const inner = (
    <>
      <BadgeCheck size={13} className="shrink-0 text-emerald-400" />
      <span className="text-faint">Materials Project</span>
      <span className="font-mono font-semibold text-copper">{b.mp_id}</span>
      {b.canonical_formula && (
        <span className="rounded-sm bg-copper/10 px-1.5 py-0.5 font-mono text-[10px] text-copper">
          {b.canonical_formula}
        </span>
      )}
      {b.url && <ExternalLink size={11} className="shrink-0 text-faint" />}
    </>
  );

  const cls =
    'inline-flex items-center gap-1.5 rounded-full border border-copper/30 bg-copper/5 ' +
    'px-2.5 py-1 text-[11px] transition';

  if (b.url) {
    return (
      <a
        href={b.url}
        target="_blank"
        rel="noopener noreferrer"
        className={`${cls} hover:border-copper/60 hover:bg-copper/10`}
        title={`Открыть ${b.mp_id} в Materials Project — канонизация подтверждена внешним авторитетом`}
      >
        {inner}
      </a>
    );
  }

  return (
    <span
      className={cls}
      title="Канонизация подтверждена внешним авторитетом Materials Project"
    >
      {inner}
    </span>
  );
}
