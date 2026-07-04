import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Boxes,
  Database,
  GitCompareArrows,
  Loader2,
  Radar,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import { api } from '../api';
import { CoverageView } from './CoverageView';
import { MaterialCoverageHeatmapView } from './MaterialCoverageHeatmapView';
import { LargeGraphView } from './LargeGraphView';

// Командный центр (agentic dashboard). The hard numbers of the knowledge graph at a
// glance — size, top technologies, per-domain coverage + the material×property coverage
// heatmap embedded inline — plus an analyst agent's narrative «state of knowledge»
// briefing written over that snapshot (DeepSeek).

export function DashboardView() {
  const q = useQuery({ queryKey: ['briefing'], queryFn: api.briefing, staleTime: 5 * 60_000 });
  const snap = q.data?.snapshot;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">состояние базы знаний</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Radar size={22} className="text-copper" /> Обзор базы знаний
        </h1>

        {q.isLoading ? (
          <div className="mt-8 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> Готовим обзор…
          </div>
        ) : (
          <>
            {/* Counters */}
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat icon={<Database size={15} />} label="Узлы" v={snap?.counts.nodes} />
              <Stat icon={<Boxes size={15} />} label="Связи" v={snap?.counts.rels} />
              <Stat
                icon={<TriangleAlert size={15} />}
                label="Пробелы"
                v={snap?.coverage.totals?.gaps}
              />
              <Stat
                icon={<GitCompareArrows size={15} />}
                label="Противоречия"
                v={snap?.coverage.totals?.contradictions}
              />
            </div>

            {/* Agent briefing */}
            <div className="panel mt-5 border-copper/30 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm text-copper">
                <Sparkles size={15} /> Аналитический обзор
                {q.data?.model && (
                  <span className="ml-auto font-mono text-[10px] text-faint">{q.data.model}</span>
                )}
              </div>
              <div className="md text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {q.data?.briefing ?? ''}
                </ReactMarkdown>
              </div>
            </div>

            {/* Покрытие по доменам — полный раздел, встроенный в обзор */}
            <div className="panel mt-5 p-4">
              <CoverageView embedded />
            </div>

            {/* Top technologies */}
            <div className="panel mt-5 p-4">
              <div className="mb-2 text-sm text-nickel">Ключевые технологии (по связям)</div>
              <div className="flex flex-wrap gap-2">
                {(snap?.topTechnologies ?? []).map((t) => (
                  <span key={t.id} className="chip text-muted">
                    {t.name}
                    <span className="ml-1 font-mono text-[10px] text-faint">{t.degree}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* Покрытие материал × свойство — тепловая карта, встроенная в обзор */}
            <div className="panel mt-5 p-4">
              <MaterialCoverageHeatmapView embedded />
            </div>

            {/* Клубок корпуса (WebGL) — встроен в обзор фиксированной высотой */}
            <div className="mt-5">
              <div className="mb-2 text-sm text-nickel">Клубок корпуса</div>
              <div className="panel h-[520px] min-h-0 overflow-hidden p-0">
                <LargeGraphView />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ icon, label, v }: { icon: React.ReactNode; label: string; v?: number }) {
  return (
    <div className="panel p-3">
      <div className="mb-1 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
        {icon}
        {label}
      </div>
      <div className="metric text-xl text-copper">{v?.toLocaleString('ru') ?? '—'}</div>
    </div>
  );
}
