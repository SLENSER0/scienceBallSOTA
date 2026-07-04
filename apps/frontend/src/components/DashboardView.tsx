import { useEffect, useRef, useState } from 'react';
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
import type { Briefing } from '../types';
import { CoverageView } from './CoverageView';
import { MaterialCoverageHeatmapView } from './MaterialCoverageHeatmapView';
import { LargeGraphView } from './LargeGraphView';
import { CommunityClusterGraphView } from './CommunityClusterGraphView';
import { ClusterMap3DView } from './ClusterMap3DView';

// Командный центр (agentic dashboard). The hard numbers of the knowledge graph at a
// glance — size, top technologies, per-domain coverage + the material×property coverage
// heatmap + the cluster map embedded inline — plus an analyst agent's narrative «state
// of knowledge» briefing written over that snapshot (DeepSeek).

// Persist the last briefing so the dashboard PAINTS INSTANTLY the moment the user logs
// in (placeholderData), then refreshes in the background instead of showing a spinner
// while the analyst agent regenerates it.
const BRIEFING_CACHE_KEY = 'sb.briefing';
function loadCachedBriefing(): Briefing | undefined {
  try {
    const raw = localStorage.getItem(BRIEFING_CACHE_KEY);
    return raw ? (JSON.parse(raw) as Briefing) : undefined;
  } catch {
    return undefined;
  }
}

export function DashboardView() {
  const q = useQuery({
    queryKey: ['briefing'],
    queryFn: api.briefing,
    staleTime: 5 * 60_000,
    placeholderData: loadCachedBriefing,
  });
  const snap = q.data?.snapshot;

  // Cache fresh briefings (never the placeholder) for the next instant login.
  useEffect(() => {
    if (q.data && !q.isPlaceholderData) {
      try {
        localStorage.setItem(BRIEFING_CACHE_KEY, JSON.stringify(q.data));
      } catch {
        /* storage may be unavailable */
      }
    }
  }, [q.data, q.isPlaceholderData]);

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
              <Stat icon={<Database size={15} />} label="Узлы" v={snap?.counts?.nodes} />
              <Stat icon={<Boxes size={15} />} label="Связи" v={snap?.counts?.rels} />
              <Stat
                icon={<TriangleAlert size={15} />}
                label="Пробелы"
                v={snap?.coverage?.totals?.gaps}
              />
              <Stat
                icon={<GitCompareArrows size={15} />}
                label="Противоречия"
                v={snap?.coverage?.totals?.contradictions}
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
                <LazyVisible>
                  <LargeGraphView />
                </LazyVisible>
              </div>
            </div>

            {/* Карта кластеров — встроена в обзор фиксированной высотой */}
            <div className="mt-5">
              <div className="mb-2 text-sm text-nickel">Карта кластеров</div>
              <div className="panel h-[520px] min-h-0 overflow-hidden p-0">
                <LazyVisible>
                  <CommunityClusterGraphView />
                </LazyVisible>
              </div>
            </div>

            {/* Карта тем корпуса (3D) — семантические кластеры эмбеддингов чанков */}
            <div className="mt-5">
              <div className="mb-2 text-sm text-nickel">Карта тем корпуса (3D)</div>
              <div className="panel h-[560px] min-h-0 overflow-hidden p-0">
                <LazyVisible>
                  <ClusterMap3DView />
                </LazyVisible>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Defer expensive WebGL panels until scrolled into view: never spin up a second
// Sigma/WebGL context or run a layout for a below-the-fold panel during first paint.
function LazyVisible({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [show, setShow] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || show) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShow(true);
          io.disconnect();
        }
      },
      { rootMargin: '200px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [show]);
  return (
    <div ref={ref} className="h-full">
      {show ? children : null}
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
