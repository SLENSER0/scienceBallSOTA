import { useEffect, useState } from 'react';
import { ArrowRight, ListChecks, RotateCw, Sparkles, Target } from 'lucide-react';
import type { PrioritizedGap } from '../types';
import { useStore } from '../store';
import { startGapMap } from '../lib/gapMapStream';
import { AgentProgress } from './AgentProgress';
import { GapDeepResearchPanel, getSolvedGaps } from './GapDeepResearchPanel';

// Карта пробелов с приоритизацией (agentic). The gap-scanner says WHERE knowledge is
// missing; a prioritization agent per gap (GLM-5.2, up to 10 in parallel) scores research
// priority — impact × feasibility + a concrete next action. Cards stream in the instant
// each agent finishes, behind an HONEST progress bar (done/total).
//
// The stream state lives in the app store (see lib/gapMapStream), so switching tabs and
// coming back shows the already-scored cards instantly — no restart.

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  environment: 'Экология',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электромет',
};

// §M12 5-way gap taxonomy → badge colour. Copper = a true hole to fill; red = sources
// disagree; amber = evidence is thin; slate = the fact is probably in a source but wasn't
// extracted; green = actually known.
const TAX5_COLOR: Record<string, string> = {
  CONTRADICTED: '#E5484D',
  WEAK_EVIDENCE: '#E0A23C',
  POSSIBLE_EXTRACTION_GAP: '#8FA3B0',
  TRUE_GAP: '#C87941',
  KNOWN: '#3FB68B',
};

function Tax5Badge({ code, label }: { code?: string | null; label?: string | null }) {
  if (!code) return null;
  const c = TAX5_COLOR[code] ?? '#8FA3B0';
  return (
    <span
      className="chip font-mono text-[10px]"
      style={{ color: c, borderColor: c, backgroundColor: `${c}1A` }}
      title={code}
    >
      {label ?? code}
    </span>
  );
}

export function GapMapView() {
  const gapMap = useStore((s) => s.gapMap);

  // Kick the stream once; startGapMap is a no-op if it already ran (cache).
  useEffect(() => {
    startGapMap();
  }, []);

  const running = gapMap.phase === 'running';
  const { gaps: allGaps, done, total } = gapMap;
  // Hide gaps already «solved» via deep research. In-session removal goes through the store
  // (closeGap); this filter is the reload/re-scan safety net so solved gaps don't resurface.
  const [solvedIds] = useState(getSolvedGaps);
  const gaps = allGaps.filter((g) => !solvedIds.has(g.id));

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow mb-1">карта пробелов · приоритизация</div>
            <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
              <Target size={22} className="text-copper" /> Куда направить исследования
            </h1>
            <p className="mt-1 text-sm text-faint">
              Пробелы в знаниях, отсортированные по важности и выполнимости — с конкретным
              следующим шагом по каждому.
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
            <AgentProgress done={done} total={total} running={running} label="пробелов оценено" />
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
          <Tax5Badge code={g.taxonomy5} label={g.taxonomy5_ru} />
        </div>
        <div className="mt-1 font-mono text-[10px] text-faint">
          не удалось оценить — это не значит, что приоритет низкий
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
            <Tax5Badge code={g.taxonomy5} label={g.taxonomy5_ru} />
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
          {/* Per-gap deep research — the card IS the context (only on scored cards). */}
          <GapDeepResearchPanel g={g} />
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
