import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ListChecks, Sparkles, Target } from 'lucide-react';
import { api } from '../api';
import type { PrioritizedGap } from '../types';
import { AgentProgress } from './AgentProgress';

// Карта пробелов с приоритизацией (agentic). The gap-scanner says WHERE knowledge is
// missing; here a prioritization agent per gap (GLM-5.2, up to 10 in parallel) scores
// research priority — impact × feasibility + a concrete next action. Cards stream in
// the instant each agent finishes, behind an HONEST progress bar (done/total).

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  environment: 'Экология',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электромет',
};

function rankGaps(gs: PrioritizedGap[]): PrioritizedGap[] {
  // Scored first (by priority), unscored last — mirrors the backend ranking.
  return [...gs].sort(
    (a, b) => Number(b.scored) - Number(a.scored) || b.priority - a.priority,
  );
}

export function GapMapView() {
  const [gaps, setGaps] = useState<PrioritizedGap[]>([]);
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [running, setRunning] = useState(true);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setGaps([]);
    setDone(0);
    setTotal(0);
    setRunning(true);
    const es = new EventSource(api.gapsPrioritizedStreamUrl(14));
    esRef.current = es;
    es.addEventListener('start', (e) => {
      setTotal(JSON.parse((e as MessageEvent).data).total ?? 0);
    });
    es.addEventListener('gap', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setDone(d.done ?? 0);
      setGaps((prev) => rankGaps([...prev, d.gap as PrioritizedGap]));
    });
    es.addEventListener('done', () => {
      setRunning(false);
      es.close();
    });
    es.addEventListener('error', () => {
      setRunning(false);
      es.close();
    });
    return () => es.close();
  }, []);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow mb-1">карта пробелов · приоритизация</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Target size={22} className="text-copper" /> Куда направить исследования
        </h1>
        <p className="mt-1 text-sm text-faint">
          Каждый пробел знаний оценивает отдельный агент-приоритизатор (
          <span className="font-mono text-copper">glm-5.2</span>, до 10 параллельно): важность ×
          осуществимость + конкретный следующий шаг. Карточки появляются по мере готовности агентов.
        </p>

        {(running || total > 0) && (
          <div className="mt-4">
            <AgentProgress done={done} total={total} running={running} label="агентов оценили" />
          </div>
        )}

        <div className="mt-5 space-y-3">
          {gaps.map((g, i) => (
            <GapCard key={g.id} g={g} rank={i + 1} />
          ))}
          {!running && gaps.length === 0 && (
            <div className="panel py-10 text-center font-mono text-[11px] text-faint">
              пробелов не найдено
            </div>
          )}
        </div>
      </div>
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
