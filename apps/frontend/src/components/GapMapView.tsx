import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowRight,
  ClipboardList,
  ListChecks,
  RotateCw,
  Sparkles,
  Target,
} from 'lucide-react';
import { api } from '../api';
import type { PrioritizedGap } from '../types';
import { useStore } from '../store';
import { startGapMap } from '../lib/gapMapStream';
import { AgentProgress } from './AgentProgress';

// Карта пробелов — единый хаб зон риска (agentic). The gap-scanner says WHERE knowledge
// is missing; a prioritization agent per gap (GLM-5.2, up to 10 in parallel) scores
// research priority — impact × feasibility + a concrete next action. Cards stream in the
// instant each agent finishes, behind an HONEST progress bar (done/total).
//
// The stream state lives in the app store (see lib/gapMapStream), so switching tabs and
// coming back shows the already-scored cards instantly — no restart. Merged in from the
// old «Пробелы и риски» screen: compact «противоречия» и «очередь ревью» sидебар so this
// one screen covers the whole risk picture.

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  environment: 'Экология',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электромет',
};

export function GapMapView() {
  const gapMap = useStore((s) => s.gapMap);
  const setView = useStore((s) => s.setView);
  const contradictions = useQuery({ queryKey: ['contradictions'], queryFn: api.contradictions });
  const queue = useQuery({ queryKey: ['queue'], queryFn: api.reviewQueue });

  // Kick the stream once; startGapMap is a no-op if it already ran (cache).
  useEffect(() => {
    startGapMap();
  }, []);

  const running = gapMap.phase === 'running';
  const { gaps, done, total } = gapMap;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow mb-1">карта пробелов · зоны риска знаний</div>
            <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
              <Target size={22} className="text-copper" /> Куда направить исследования
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-faint">
              Каждый пробел знаний оценивает отдельный агент-приоритизатор (
              <span className="font-mono text-copper">glm-5.2</span>, до 10 параллельно): важность ×
              осуществимость + конкретный следующий шаг. Карточки появляются по мере готовности
              агентов.
            </p>
          </div>
          <button
            onClick={() => startGapMap(true)}
            disabled={running}
            className="chip flex shrink-0 items-center gap-1.5 border-line text-faint hover:text-ink disabled:opacity-40"
            title="Пересчитать приоритеты заново"
          >
            <RotateCw size={12} className={running ? 'animate-spin' : ''} /> обновить
          </button>
        </div>

        {(running || total > 0) && (
          <div className="mt-4">
            <AgentProgress done={done} total={total} running={running} label="агентов оценили" />
          </div>
        )}

        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_18rem]">
          {/* Приоритизированные пробелы — the hero column */}
          <div className="space-y-3">
            {gaps.map((g, i) => (
              <GapCard key={g.id} g={g} rank={i + 1} />
            ))}
            {!running && gaps.length === 0 && (
              <div className="panel py-10 text-center font-mono text-[11px] text-faint">
                пробелов не найдено
              </div>
            )}
          </div>

          {/* Сводка рисков — absorbed from the old «Пробелы и риски» screen */}
          <div className="space-y-4">
            <SummaryPanel
              icon={<AlertTriangle size={14} />}
              tone="contradiction"
              title="Противоречия"
              count={contradictions.data?.count ?? 0}
              action={{ label: 'арбитр →', onClick: () => setView('contradictions') }}
            >
              {(contradictions.data?.contradictions ?? []).slice(0, 5).map((c) => (
                <li key={c.id} className="truncate text-ink/85">
                  {c.name}
                </li>
              ))}
            </SummaryPanel>

            <SummaryPanel
              icon={<ClipboardList size={14} />}
              tone="nickel"
              title="Очередь ревью"
              count={queue.data?.items.length ?? 0}
              action={{ label: 'курирование →', onClick: () => setView('curation') }}
            >
              {(queue.data?.items ?? []).slice(0, 5).map((it) => (
                <li key={it.id} className="truncate text-ink/85">
                  <span className="font-mono text-[10px] text-faint">{it.label}</span> {it.name}
                  {it.confidence != null && (
                    <span className="ml-1 metric text-[10px] text-faint">
                      {Math.round(it.confidence * 100)}%
                    </span>
                  )}
                </li>
              ))}
            </SummaryPanel>
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryPanel({
  icon,
  tone,
  title,
  count,
  action,
  children,
}: {
  icon: React.ReactNode;
  tone: 'contradiction' | 'nickel';
  title: string;
  count: number;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
}) {
  const color = tone === 'contradiction' ? 'text-contradiction' : 'text-nickel';
  return (
    <div className="panel p-4">
      <div className={`mb-2.5 flex items-center gap-2 font-mono text-xs uppercase tracking-wide ${color}`}>
        {icon}
        {title}
        <span className="ml-auto metric text-base text-ink">{count}</span>
      </div>
      <ul className="space-y-1.5 text-[13px]">{children}</ul>
      {action && (
        <button
          onClick={action.onClick}
          className="mt-3 font-mono text-[10px] uppercase tracking-wide text-faint hover:text-copper-bright"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

function GapCard({ g, rank }: { g: PrioritizedGap; rank: number }) {
  const tone = g.priority >= 75 ? '#E5484D' : g.priority >= 55 ? '#E0A23C' : '#8FA3B0';
  if (!g.scored) {
    return (
      <div className="panel p-4 opacity-70">
        <div className="flex items-center gap-2">
          <span className="chip text-faint border-line">не оценён</span>
          <span className="text-sm text-muted">{g.name}</span>
          {g.domain && <span className="chip text-faint">{DOMAIN_RU[g.domain] ?? g.domain}</span>}
        </div>
        <div className="mt-1 font-mono text-[10px] text-faint">
          агент не смог оценить (сбой модели) — не значит низкий приоритет
        </div>
      </div>
    );
  }
  return (
    <div className="panel p-4">
      <div className="flex items-start gap-3">
        <div className="flex flex-col items-center">
          <span className="metric text-lg" style={{ color: tone }}>
            {g.priority}
          </span>
          <span className="font-mono text-[9px] text-faint">#{rank}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink">{g.name}</span>
            {g.domain && <span className="chip text-faint">{DOMAIN_RU[g.domain] ?? g.domain}</span>}
          </div>
          {g.rationale && <div className="mt-1 text-[13px] text-muted">{g.rationale}</div>}
          {g.action && (
            <div className="mt-2 flex items-start gap-1.5 text-[13px] text-copper-bright">
              <ArrowRight size={13} className="mt-0.5 shrink-0" />
              <span>{g.action}</span>
            </div>
          )}
          {/* impact / feasibility mini-bars */}
          <div className="mt-2 flex gap-4">
            <MiniBar label="важность" v={g.impact} icon={<Sparkles size={10} />} />
            <MiniBar label="осуществимость" v={g.feasibility} icon={<ListChecks size={10} />} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniBar({ label, v, icon }: { label: string; v: number; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="flex items-center gap-0.5 font-mono text-[9px] uppercase tracking-wide text-faint">
        {icon} {label}
      </span>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-copper/60" style={{ width: `${v}%` }} />
      </div>
      <span className="font-mono text-[9px] text-faint">{v}</span>
    </div>
  );
}
