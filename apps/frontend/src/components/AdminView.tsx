import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Coins,
  Database,
  GitBranch,
  Grid3x3,
  Loader2,
  ScrollText,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../api';

// Экран Admin: metadata, lineage, governance, audit (§17.20 / Phase 8). A read-only
// governance dashboard over the live graph: node/relationship distribution, extractor
// lineage runs, coverage matrix size, techno-economic indicators, and the audit tail.

export function AdminView() {
  const stats = useQuery({ queryKey: ['admin-stats'], queryFn: api.stats });
  const lineage = useQuery({ queryKey: ['admin-lineage'], queryFn: api.adminLineage });
  const matrix = useQuery({ queryKey: ['admin-matrix'], queryFn: api.adminCoverageMatrix });
  const tech = useQuery({ queryKey: ['admin-tech'], queryFn: api.adminTechnoeconomic });
  const audit = useQuery({ queryKey: ['admin-audit'], queryFn: () => api.auditTail(40) });

  const byLabel = Object.entries(stats.data?.by_label ?? {}).sort((a, b) => b[1] - a[1]);
  const maxCount = byLabel[0]?.[1] ?? 1;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">Администрирование · governance</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <ShieldCheck size={22} className="text-copper" /> Панель управления графом
        </h1>

        {/* Top counters */}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Counter
            icon={<Database size={15} />}
            label="Узлы"
            value={stats.data?.counts.nodes}
            loading={stats.isLoading}
          />
          <Counter
            icon={<GitBranch size={15} />}
            label="Связи"
            value={stats.data?.counts.rels}
            loading={stats.isLoading}
          />
          <Counter
            icon={<Grid3x3 size={15} />}
            label="Матрица покрытия"
            value={matrix.data?.matrix.materials.length}
            suffix="матер."
            loading={matrix.isLoading}
          />
          <Counter
            icon={<Coins size={15} />}
            label="Технико-эконом."
            value={tech.data?.solutions.length}
            suffix="решений"
            loading={tech.isLoading}
          />
        </div>

        {/* Node distribution */}
        <Section icon={<Database size={15} />} title="Распределение узлов по типам">
          <div className="space-y-1.5">
            {byLabel.map(([label, n]) => (
              <div key={label} className="flex items-center gap-2">
                <span className="w-40 shrink-0 truncate font-mono text-[11px] text-muted">{label}</span>
                <div className="h-3 flex-1 overflow-hidden rounded-sm bg-line/60">
                  <div
                    className="h-full rounded-sm bg-copper/60"
                    style={{ width: `${Math.max(2, (n / maxCount) * 100)}%` }}
                  />
                </div>
                <span className="metric w-16 shrink-0 text-right text-xs text-nickel">
                  {n.toLocaleString('ru')}
                </span>
              </div>
            ))}
          </div>
        </Section>

        {/* Lineage runs */}
        <Section icon={<Activity size={15} />} title="Lineage · прогоны экстрактора">
          {lineage.isLoading ? (
            <Loading />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left font-mono text-[10px] uppercase tracking-wide text-faint">
                    <th className="px-2 py-1">run</th>
                    <th className="px-2 py-1">тип</th>
                    <th className="px-2 py-1">создан</th>
                    <th className="px-2 py-1 text-right">узлов</th>
                  </tr>
                </thead>
                <tbody>
                  {(lineage.data?.runs ?? []).map((r) => (
                    <tr key={r.run_id} className="border-t border-line/60">
                      <td className="px-2 py-1.5 font-mono text-[11px] text-ink">{r.name}</td>
                      <td className="px-2 py-1.5 text-muted">{r.type}</td>
                      <td className="px-2 py-1.5 font-mono text-[11px] text-faint">
                        {String(r.created_at).slice(0, 10)}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-[11px] text-nickel">
                        {Object.values(r.by_label).reduce((a, b) => a + b, 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* Audit log */}
        <Section icon={<ScrollText size={15} />} title="Журнал аудита (последние действия)">
          {audit.isLoading ? (
            <Loading />
          ) : (audit.data?.entries.length ?? 0) === 0 ? (
            <div className="font-mono text-[11px] text-faint">
              нет записей или недостаточно прав
            </div>
          ) : (
            <ul className="space-y-1">
              {(audit.data?.entries ?? [])
                .slice()
                .reverse()
                .map((e, i) => (
                  <li key={i} className="flex items-center gap-2 font-mono text-[11px]">
                    <span className="text-faint">{new Date(e.ts * 1000).toLocaleTimeString('ru')}</span>
                    <span className="chip text-copper">{e.action}</span>
                    <span className="text-muted">{e.role}</span>
                    <span className="truncate text-faint">
                      {e.detail ? JSON.stringify(e.detail).slice(0, 90) : ''}
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Section>
      </div>
    </div>
  );
}

function Counter({
  icon,
  label,
  value,
  suffix,
  loading,
}: {
  icon: React.ReactNode;
  label: string;
  value?: number;
  suffix?: string;
  loading?: boolean;
}) {
  return (
    <div className="panel p-3">
      <div className="mb-1 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
        {icon}
        {label}
      </div>
      <div className="metric text-xl text-copper">
        {loading ? '…' : (value?.toLocaleString('ru') ?? '—')}
        {suffix && !loading && <span className="ml-1 text-[11px] text-faint">{suffix}</span>}
      </div>
    </div>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel mt-5 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-nickel">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}

function Loading() {
  return (
    <div className="flex items-center gap-2 font-mono text-xs text-faint">
      <Loader2 size={14} className="animate-spin text-copper" /> загрузка…
    </div>
  );
}
