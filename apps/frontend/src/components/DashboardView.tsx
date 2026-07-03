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

// Командный центр (agentic dashboard). The hard numbers of the knowledge graph at a
// glance — size, per-domain coverage + risk, top technologies — plus an analyst agent's
// narrative «state of knowledge» briefing written over that snapshot (DeepSeek).

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидрометаллургия',
  pyrometallurgy: 'Пирометаллургия',
  environment: 'Экология',
  waste_processing: 'Переработка отходов',
  water_treatment: 'Водоочистка',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электрометаллургия',
  unknown: 'Без домена',
  'без домена': 'Без домена',
};

export function DashboardView() {
  const q = useQuery({ queryKey: ['briefing'], queryFn: api.briefing, staleTime: 5 * 60_000 });
  const snap = q.data?.snapshot;
  const domains = (snap?.coverage.by_domain ?? []).filter((d) => d.domain !== 'без домена');
  const maxSrc = Math.max(1, ...domains.map((d) => d.sources));

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">командный центр · состояние знаний</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Radar size={22} className="text-copper" /> Обзор базы знаний
        </h1>

        {q.isLoading ? (
          <div className="mt-8 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> агент-аналитик готовит обзор…
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
                <Sparkles size={15} /> Аналитический обзор (агент)
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

            {/* Domain coverage bars */}
            <div className="panel mt-5 p-4">
              <div className="mb-3 text-sm text-nickel">Покрытие по доменам</div>
              <div className="space-y-1.5">
                {domains.map((d) => (
                  <div key={d.domain} className="flex items-center gap-2">
                    <span className="w-40 shrink-0 truncate text-xs text-muted">
                      {DOMAIN_RU[d.domain] ?? d.domain}
                    </span>
                    <div className="h-3 flex-1 overflow-hidden rounded-sm bg-line/60">
                      <div
                        className={`h-full rounded-sm ${d.risk === 'high' ? 'bg-contradiction/60' : 'bg-copper/60'}`}
                        style={{ width: `${Math.max(3, (d.sources / maxSrc) * 100)}%` }}
                      />
                    </div>
                    <span className="metric w-24 shrink-0 text-right text-[11px] text-nickel">
                      {d.sources} ист.
                      {d.risk === 'high' && <span className="ml-1 text-contradiction">риск</span>}
                    </span>
                  </div>
                ))}
              </div>
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
