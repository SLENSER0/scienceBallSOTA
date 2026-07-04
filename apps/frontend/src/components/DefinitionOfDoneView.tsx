import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CircleCheck,
  CircleSlash,
  CircleMinus,
  Download,
  Gauge,
  Loader2,
  Play,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';

// §22.7 — Summary Definition-of-Done CI-gate. One aggregating job that folds
// phase-checks + eval + e2e into a single GREEN/YELLOW/RED verdict + release
// artifact. Self-contained (no api.ts edits): it calls the definition-of-done
// router directly with the same session-auth convention as api.ts.

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

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

interface CheckRow {
  id: string;
  phase: string;
  title: string;
  required: boolean;
  passed: boolean;
  skipped: boolean;
  status: string;
  detail: string;
  metric: number | null;
  threshold: number | null;
  extra?: Record<string, unknown>;
}
interface PhaseBlock {
  phase: string;
  verdict: string;
  passed: number;
  total: number;
  checks: CheckRow[];
}
interface DodSummary {
  green: number;
  red: number;
  skipped: number;
  total: number;
  required_total: number;
  readiness_pct: number;
  elapsed_ms: number;
}
interface DodReport {
  verdict: string;
  generated_at: string;
  runtime_profile: string;
  summary: DodSummary;
  phases: PhaseBlock[];
  checks: CheckRow[];
  meta: {
    spec: string;
    min_health: number;
    eval_gates: Record<string, number>;
    reused: string[];
  };
}

const VERDICT_STYLE: Record<string, { ring: string; text: string; label: string }> = {
  GREEN: { ring: 'border-emerald-500/50', text: 'text-emerald-400', label: 'GREEN' },
  YELLOW: { ring: 'border-amber-500/50', text: 'text-amber-400', label: 'YELLOW' },
  RED: { ring: 'border-red-500/50', text: 'text-red-400', label: 'RED' },
};

const PHASE_LABEL: Record<string, string> = {
  'phase-checks': 'Фаза 1 · phase-checks (структура + инфра + health)',
  eval: 'Фаза 2 · eval (golden + data-quality gates)',
  e2e: 'Фаза 3 · e2e (5 сценариев §2.1 против живого стора)',
};

function VerdictIcon({ verdict, size = 28 }: { verdict: string; size?: number }) {
  if (verdict === 'GREEN') return <CircleCheck size={size} className="text-emerald-400" />;
  if (verdict === 'YELLOW') return <TriangleAlert size={size} className="text-amber-400" />;
  return <CircleSlash size={size} className="text-red-400" />;
}

function StatusChip({ check }: { check: CheckRow }) {
  if (check.skipped) {
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-faint">
        <CircleMinus size={14} /> пропущено
      </span>
    );
  }
  if (check.passed) {
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-emerald-400">
        <CircleCheck size={14} /> green
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-xs font-medium text-red-400">
      <CircleSlash size={14} /> red
    </span>
  );
}

function fmtMetric(v: number | null): string {
  if (v === null || v === undefined) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
}

export default function DefinitionOfDoneView() {
  const base = '/api/v1/definition-of-done';
  const gate = useQuery({
    queryKey: ['dod-gate'],
    queryFn: () => apiGet<DodReport>(`${base}/gate`),
    refetchOnWindowFocus: false,
  });

  const report = gate.data;
  const style = useMemo(
    () => (report ? VERDICT_STYLE[report.verdict] ?? VERDICT_STYLE.RED : null),
    [report],
  );

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">Definition of Done · §22.7</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Сводный CI-gate готовности v1.0</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Единый агрегирующий джоб сворачивает phase-checks + eval + e2e в одну
          галочку GREEN/YELLOW/RED и прикрепляемый release-артефакт. Проверки идут
          против живого графа (Neo4j в server-профиле), переиспользуя уже
          отгруженные модули health / golden / quality-gates / gap-scan.
        </p>

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => gate.refetch()}
            disabled={gate.isFetching}
            className="btn-copper flex items-center gap-2"
          >
            {gate.isFetching ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            Прогнать gate
          </button>
          <a
            href={`${base}/artifact`}
            className="flex items-center gap-1 text-sm text-copper underline-offset-2 hover:underline"
          >
            <Download size={15} /> Скачать артефакт (JSON)
          </a>
          {report && (
            <span className="text-xs text-faint">
              профиль {report.runtime_profile} · {report.summary.elapsed_ms} мс ·{' '}
              {new Date(report.generated_at).toLocaleString()}
            </span>
          )}
        </div>

        {gate.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Не удалось прогнать gate: {(gate.error as Error)?.message}
          </div>
        )}

        {gate.isLoading && !report && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Прогоняем сводный gate…
          </div>
        )}

        {report && style && (
          <div className="space-y-6">
            {/* Verdict banner */}
            <div className={`panel flex items-center gap-4 border p-4 ${style.ring}`}>
              <VerdictIcon verdict={report.verdict} />
              <div className="flex-1">
                <div className="font-display text-lg text-ink">
                  Definition of Done:{' '}
                  <span className={style.text}>{style.label}</span>
                </div>
                <div className="text-sm text-faint">
                  {report.summary.green}/{report.summary.total} проверок зелёные ·{' '}
                  {report.summary.red} красных · {report.summary.skipped} пропущено ·{' '}
                  {report.summary.required_total} обязательных
                </div>
              </div>
              <div className="flex items-center gap-2 text-right">
                <Gauge size={18} className={style.text} />
                <div>
                  <div className={`font-display text-2xl ${style.text}`}>
                    {report.summary.readiness_pct}%
                  </div>
                  <div className="text-xs text-faint">готовность</div>
                </div>
              </div>
            </div>

            {/* Per-phase breakdown */}
            {report.phases.map((ph) => {
              const ps = VERDICT_STYLE[ph.verdict] ?? VERDICT_STYLE.RED;
              return (
                <div key={ph.phase} className="panel p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <VerdictIcon verdict={ph.verdict} size={18} />
                    <h3 className="font-display text-lg">
                      {PHASE_LABEL[ph.phase] ?? ph.phase}
                    </h3>
                    <span className={`ml-auto text-sm ${ps.text}`}>
                      {ph.passed}/{ph.total} · {ph.verdict}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {ph.checks.map((c) => (
                      <div
                        key={c.id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-white/5 px-3 py-2 text-sm"
                      >
                        <StatusChip check={c} />
                        <span className="text-ink">{c.title}</span>
                        {!c.required && (
                          <span className="text-[10px] uppercase tracking-wide text-faint">
                            soft
                          </span>
                        )}
                        <span className="ml-auto font-mono text-xs text-faint">
                          {c.detail}
                        </span>
                        {c.threshold !== null && (
                          <span className="font-mono text-xs text-faint">
                            [{fmtMetric(c.metric)} / {fmtMetric(c.threshold)}]
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}

            {/* Reused modules provenance */}
            <div className="panel p-4">
              <div className="mb-2 flex items-center gap-2 text-sm text-faint">
                <ShieldCheck size={15} /> {report.meta.spec}
              </div>
              <div className="text-xs text-faint">
                min-health {report.meta.min_health} · eval-gates{' '}
                {Object.entries(report.meta.eval_gates)
                  .map(([k, v]) => `${k}≥${v}`)
                  .join(', ')}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {report.meta.reused.map((m) => (
                  <span
                    key={m}
                    className="rounded bg-white/5 px-2 py-0.5 font-mono text-[11px] text-faint"
                  >
                    {m}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
