import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FlaskConical, Target, CheckCircle2, CircleDashed, Coins, Layers } from 'lucide-react';
import { api } from '../api';

/** §15.9 — minimal set of experiments that closes the most open gaps. */
export interface ClosureGapCard {
  id: string;
  name: string;
  gap_type: string;
  domain: string | null;
  subject: string;
  weight: number;
}
export interface ClosureExperiment {
  experiment_id: string;
  kind: string | null;
  title: string;
  facet: string | null;
  detail: string | null;
  cost: number;
  n_gaps_closed: number;
  gaps: ClosureGapCard[];
}
export interface ClosurePlanResponse {
  headline: string;
  summary: {
    n_experiments: number;
    n_gaps_total: number;
    n_gaps_closed: number;
    n_gaps_uncovered: number;
    coverage_ratio: number;
    weighted_coverage_ratio: number;
    total_cost: number;
  };
  experiments: ClosureExperiment[];
  uncovered: ClosureGapCard[];
}

const CAPS = [
  { label: 'Мин. набор', value: undefined as number | undefined },
  { label: '1', value: 1 },
  { label: '2', value: 2 },
  { label: '3', value: 3 },
  { label: '5', value: 5 },
];

export function GapClosurePlanView() {
  const [cap, setCap] = useState<number | undefined>(undefined);
  const plan = useQuery({
    queryKey: ['gap-closure-plan', cap],
    queryFn: () => api.gapClosurePlan(cap),
  });

  const d = plan.data;
  const s = d?.summary;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">приоритизация · §15.9</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">План закрытия пробелов</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          Минимальный набор экспериментов, который закрывает больше всего открытых пробелов —
          жадный set-cover по приоритету пробелов.
        </p>

        {/* headline banner */}
        <div className="panel mb-4 flex items-center gap-3 border-l-2 border-nickel/60 p-4">
          <Target size={18} className="text-nickel" />
          <div className="font-display text-lg font-semibold text-ink">
            {plan.isLoading ? 'Считаем план…' : plan.isError ? 'Не удалось построить план' : d?.headline}
          </div>
        </div>

        {/* experiment-count cap selector */}
        <div className="mb-5 flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-faint">Лимит экспериментов:</span>
          {CAPS.map((c) => (
            <button
              key={c.label}
              onClick={() => setCap(c.value)}
              className={`rounded px-2.5 py-1 font-mono text-xs transition ${
                cap === c.value ? 'bg-nickel/20 text-nickel' : 'text-faint hover:text-ink'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* KPI tiles */}
        {s && (
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi icon={<FlaskConical size={14} />} label="Экспериментов" value={s.n_experiments} tone="nickel" />
            <Kpi
              icon={<CheckCircle2 size={14} />}
              label="Пробелов закрыто"
              value={`${s.n_gaps_closed}/${s.n_gaps_total}`}
              tone="gap"
            />
            <Kpi
              icon={<Layers size={14} />}
              label="Покрытие"
              value={`${Math.round(s.coverage_ratio * 100)}%`}
              tone="nickel"
            />
            <Kpi icon={<Coins size={14} />} label="Суммарная стоимость" value={s.total_cost} tone="nickel" />
          </div>
        )}

        {/* experiment cards */}
        <div className="space-y-3">
          {d?.experiments.map((e, i) => (
            <div key={e.experiment_id} className="panel p-4">
              <div className="mb-2 flex items-start gap-3">
                <div className="metric mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-nickel/15 text-xs text-nickel">
                  {i + 1}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-base font-semibold text-ink">{e.title}</span>
                    {e.kind && (
                      <span className="rounded bg-ink/5 px-1.5 py-0.5 font-mono text-[10px] uppercase text-faint">
                        {e.kind === 'focused' ? 'фокус' : 'кампания'}
                      </span>
                    )}
                  </div>
                  {e.detail && <div className="mt-0.5 font-mono text-[11px] text-faint">{e.detail}</div>}
                </div>
                <div className="text-right">
                  <div className="metric text-lg text-gap">−{e.n_gaps_closed}</div>
                  <div className="font-mono text-[10px] text-faint">стоимость {e.cost}</div>
                </div>
              </div>
              <ul className="ml-9 space-y-1 border-l border-ink/10 pl-3 text-sm">
                {e.gaps.map((g) => (
                  <li key={g.id} className="flex items-center gap-2 text-ink/85">
                    <CheckCircle2 size={12} className="shrink-0 text-gap" />
                    <span className="truncate">{g.name}</span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-faint">
                      {g.gap_type} · w{g.weight.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* uncovered gaps */}
        {d && d.uncovered.length > 0 && (
          <div className="panel mt-5 p-4">
            <div className="mb-3 flex items-center gap-2 font-mono text-xs uppercase tracking-wide text-faint">
              <CircleDashed size={14} />
              Останутся открытыми ({d.uncovered.length})
            </div>
            <ul className="space-y-1 text-sm">
              {d.uncovered.map((g) => (
                <li key={g.id} className="flex items-center gap-2 text-ink/70">
                  <CircleDashed size={12} className="shrink-0 text-faint" />
                  <span className="truncate">{g.name}</span>
                  <span className="ml-auto shrink-0 font-mono text-[10px] text-faint">{g.gap_type}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  tone: 'nickel' | 'gap';
}) {
  const color = tone === 'gap' ? 'text-gap' : 'text-nickel';
  return (
    <div className="panel p-3">
      <div className={`mb-1 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide ${color}`}>
        {icon}
        {label}
      </div>
      <div className="metric text-2xl text-ink">{value}</div>
    </div>
  );
}
