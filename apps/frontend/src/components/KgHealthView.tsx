import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  HeartPulse,
  Loader2,
  ShieldAlert,
} from 'lucide-react';

// §23.24 — KG Health Score 0–100 + data-quality scorecard (Admin).
// Surfaces the already-shipped composite scorer (kg_eval.kg_health_score) and
// per-slice breakdown (kg_eval.kg_health_slice_breakdown) via the new backend
// endpoint GET /api/v1/admin/kg-health: one health number with a letter grade,
// a component scorecard (evidence coverage / orphans / duplicates /
// contradictions / staleness), a demo/CI gate, and the graph's worst areas by
// lab / material / property / source-type slice — matching the §23.24 acceptance
// ("returns score and breakdown; dashboard shows the graph's worst areas").
//
// Self-contained fetch (reads the session token like api.ts) so it needs no
// edits to shared hub files; swap to `api.kgHealth(...)` once that method is
// wired.

interface Component {
  name: string;
  label: string;
  raw: number;
  weight: number;
  contribution: number;
  healthy: boolean;
  lower_is_better: boolean;
}

interface Slice {
  slice: string;
  score: number;
  grade: string;
  gate_passed: boolean;
  size: number;
  metrics: Record<string, number>;
}

interface Census {
  nodes: number;
  claims: number;
  entities: number;
  dated_sources: number;
  orphans: number;
  duplicates: number;
  evidenced: number;
  contradicted: number;
  stale: number;
  by_label: Record<string, number>;
}

interface KgHealthReport {
  score: number;
  grade: string;
  gate_passed: boolean;
  failing: string[];
  components: Component[];
  metrics_raw: Record<string, number>;
  dimension: string;
  census: Census;
  breakdown: {
    n: number;
    mean_score: number;
    worst: string[];
    all_gates_passed: boolean;
    slices: Slice[];
  };
  thresholds: Record<string, number>;
  weights: Record<string, number>;
  stale_cutoff_year: number;
  gate: { min_score: number; passed: boolean };
}

const DIMENSIONS: { id: string; ru: string }[] = [
  { id: 'domain', ru: 'по домену' },
  { id: 'material', ru: 'по материалу' },
  { id: 'property', ru: 'по свойству' },
  { id: 'source_type', ru: 'по типу источника' },
];

function authHeaders(): Record<string, string> {
  try {
    const raw = localStorage.getItem('sb.session');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.token) return { Authorization: `Bearer ${s.token}` };
      if (s?.role) return { 'X-Role': s.role };
    }
  } catch {
    /* ignore */
  }
  return {};
}

async function getReport(url: string): Promise<KgHealthReport> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<KgHealthReport>;
}

function scoreCls(score: number): string {
  if (score >= 90) return 'text-verified';
  if (score >= 75) return 'text-verified';
  if (score >= 60) return 'text-gap';
  return 'text-contradiction';
}

function barCls(score: number): string {
  if (score >= 75) return 'bg-verified';
  if (score >= 60) return 'bg-gap';
  return 'bg-contradiction';
}

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function KgHealthView() {
  const [dimension, setDimension] = useState<string>('domain');
  const report = useQuery({
    queryKey: ['kg-health', dimension],
    queryFn: () => getReport(`/api/v1/admin/kg-health?dimension=${dimension}`),
  });
  const data = report.data;

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col overflow-y-auto p-6">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm text-nickel">
            <HeartPulse size={16} className="text-copper" /> Здоровье графа знаний
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-faint">
            единая метрика 0–100 + data-quality scorecard и худшие зоны графа (§23.24)
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {DIMENSIONS.map((d) => (
            <button
              key={d.id}
              onClick={() => setDimension(d.id)}
              className={`chip cursor-pointer ${
                dimension === d.id
                  ? 'text-copper border-copper/50'
                  : 'text-faint border-line hover:text-nickel'
              }`}
            >
              {d.ru}
            </button>
          ))}
        </div>
      </header>

      {report.isLoading ? (
        <div className="flex items-center gap-2 font-mono text-[12px] text-faint">
          <Loader2 size={14} className="animate-spin text-copper" /> сканирование графа…
        </div>
      ) : report.isError ? (
        <div className="text-sm text-contradiction">Не удалось посчитать здоровье графа.</div>
      ) : data ? (
        <>
          <div className="mb-4 grid gap-4 md:grid-cols-[minmax(0,240px)_1fr]">
            <ScoreCard report={data} />
            <Scorecard components={data.components} thresholds={data.thresholds} />
          </div>
          <CensusStrip census={data.census} />
          <WorstAreas report={data} />
        </>
      ) : null}
    </div>
  );
}

function ScoreCard({ report }: { report: KgHealthReport }) {
  const passed = report.gate.passed;
  return (
    <div className="panel flex flex-col items-center justify-center p-5">
      <div className="font-mono text-[10px] uppercase tracking-wide text-faint">
        общий score
      </div>
      <div className={`metric mt-1 text-6xl leading-none ${scoreCls(report.score)}`}>
        {Math.round(report.score)}
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className={`chip ${scoreCls(report.score)} border-line`}>
          оценка {report.grade}
        </span>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded bg-surface/60">
        <div
          className={`h-full rounded transition-all ${barCls(report.score)}`}
          style={{ width: `${Math.max(2, Math.round(report.score))}%` }}
        />
      </div>
      <div
        className={`mt-3 flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] ${
          passed
            ? 'border-verified/40 bg-verified/10 text-verified'
            : 'border-contradiction/50 bg-contradiction/10 text-contradiction'
        }`}
      >
        {passed ? <BadgeCheck size={13} /> : <ShieldAlert size={13} />}
        {passed ? 'демо-порог пройден' : 'ниже демо-порога'}
        <span className="font-mono text-[10px] opacity-70">≥{report.gate.min_score}</span>
      </div>
    </div>
  );
}

function Scorecard({
  components,
  thresholds,
}: {
  components: Component[];
  thresholds: Record<string, number>;
}) {
  return (
    <div className="panel p-4">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-faint">
        покомпонентная разбивка (вес · порог)
      </div>
      <div className="space-y-2.5">
        {components.map((c) => {
          // "higher is better" value: invert lower-is-better raw for the bar.
          const effective = c.lower_is_better ? 1 - c.raw : c.raw;
          const limit = thresholds[c.name];
          return (
            <div key={c.name}>
              <div className="flex items-center justify-between text-[12px]">
                <span className="flex items-center gap-1.5 text-ink/90">
                  {!c.healthy && <AlertTriangle size={12} className="text-contradiction" />}
                  {c.label}
                </span>
                <span className="font-mono text-[11px] text-faint">
                  {c.lower_is_better ? pct(c.raw) : pct(effective)}
                  <span className="ml-1.5 opacity-60">×{c.weight}</span>
                </span>
              </div>
              <div className="relative mt-1 h-2 w-full overflow-hidden rounded bg-surface/60">
                <div
                  className={`h-full rounded transition-all ${
                    c.healthy ? 'bg-verified' : 'bg-contradiction'
                  }`}
                  style={{ width: `${Math.max(2, Math.round(effective * 100))}%` }}
                />
                {limit != null && (
                  <div
                    className="absolute top-0 h-full w-px bg-nickel/70"
                    style={{ left: `${Math.round(limit * 100)}%` }}
                    title={`порог ${pct(limit)}`}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CensusStrip({ census }: { census: Census }) {
  const cells: { label: string; value: string; warn?: boolean }[] = [
    { label: 'узлов', value: census.nodes.toLocaleString('ru-RU') },
    { label: 'утверждений', value: census.claims.toLocaleString('ru-RU') },
    { label: 'сущностей', value: census.entities.toLocaleString('ru-RU') },
    { label: 'источников', value: census.dated_sources.toLocaleString('ru-RU') },
    { label: 'сироты', value: String(census.orphans), warn: census.orphans > 0 },
    { label: 'дубликаты', value: String(census.duplicates), warn: census.duplicates > 0 },
    {
      label: 'противоречия',
      value: String(census.contradicted),
      warn: census.contradicted > 0,
    },
    { label: 'устарели', value: String(census.stale), warn: census.stale > 0 },
  ];
  return (
    <div className="panel mb-4 flex flex-wrap gap-x-6 gap-y-2 p-3">
      {cells.map((c) => (
        <div key={c.label} className="flex flex-col">
          <span className={`metric text-lg ${c.warn ? 'text-gap' : 'text-ink/90'}`}>
            {c.value}
          </span>
          <span className="font-mono text-[10px] text-faint">{c.label}</span>
        </div>
      ))}
    </div>
  );
}

function WorstAreas({ report }: { report: KgHealthReport }) {
  const slices = report.breakdown.slices;
  if (slices.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-faint">
        <Activity size={14} /> Нет срезов для выбранной оси.
      </div>
    );
  }
  const worst = new Set(report.breakdown.worst);
  return (
    <div className="panel overflow-x-auto">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="font-mono text-[10px] uppercase tracking-wide text-faint">
          худшие зоны графа · {report.dimension}
        </span>
        <span className="font-mono text-[10px] text-faint">
          среднее {Math.round(report.breakdown.mean_score)} · срезов {report.breakdown.n}
        </span>
      </div>
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead>
          <tr className="border-b border-line font-mono text-[10px] uppercase tracking-wide text-faint">
            <th className="px-3 py-2">Срез</th>
            <th className="px-3 py-2">Score</th>
            <th className="px-3 py-2">Узлов</th>
            <th className="px-3 py-2">Evidence</th>
            <th className="px-3 py-2">Сироты</th>
            <th className="px-3 py-2">Дубли</th>
            <th className="px-3 py-2">Противор.</th>
            <th className="px-3 py-2">Устарев.</th>
          </tr>
        </thead>
        <tbody>
          {slices.map((s) => (
            <tr
              key={s.slice}
              className={`border-b border-line/60 align-middle ${
                worst.has(s.slice) ? 'bg-contradiction/5' : ''
              }`}
            >
              <td className="px-3 py-2">
                <span className="flex items-center gap-1.5 text-ink/90">
                  {worst.has(s.slice) && (
                    <AlertTriangle size={12} className="shrink-0 text-contradiction" />
                  )}
                  {s.slice}
                </span>
              </td>
              <td className="px-3 py-2">
                <span className={`font-mono text-[12px] ${scoreCls(s.score)}`}>
                  {Math.round(s.score)}
                </span>
                <span className="ml-1 text-faint">/{s.grade}</span>
              </td>
              <td className="px-3 py-2 font-mono text-[11px] text-faint">{s.size}</td>
              <MetricCell v={s.metrics.evidence_coverage} higherBetter />
              <MetricCell v={s.metrics.orphan_rate} />
              <MetricCell v={s.metrics.duplicate_rate} />
              <MetricCell v={s.metrics.contradiction_rate} />
              <MetricCell v={s.metrics.stale_rate} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricCell({ v, higherBetter = false }: { v: number | undefined; higherBetter?: boolean }) {
  if (v == null) {
    return <td className="px-3 py-2 text-faint">—</td>;
  }
  // Colour: green = good. For rate metrics lower is better; for coverage higher.
  const good = higherBetter ? v >= 0.6 : v <= 0.2;
  const mid = higherBetter ? v >= 0.4 : v <= 0.4;
  const cls = good ? 'text-verified' : mid ? 'text-gap' : 'text-contradiction';
  return <td className={`px-3 py-2 font-mono text-[11px] ${cls}`}>{pct(v)}</td>;
}
