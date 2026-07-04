import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertOctagon,
  AlertTriangle,
  BadgeCheck,
  Clock,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

// §23.27 — Source trust / retractions / freshness on citations + verifier.
// Surfaces the already-shipped trust/freshness/retraction fusion
// (backend: /api/v1/source-trust): every citation shows its trust tier, freshness
// and any warning («источник отозван / устарел / непроверен»), and the panel makes
// the verifier's confidence penalty visible — a retracted primary source is still
// listed but drags the answer confidence down, matching the §23.27 acceptance.
//
// Self-contained fetch (reads the session token like api.ts) so it needs no edits
// to shared hub files; swap to `api.sourceTrust*` once those methods are wired.

interface CitationTrust {
  doc_id: string;
  source_status: string;
  trust_score: number;
  trust_tier: string;
  freshness_level: string;
  age_days: number | null;
  primary: boolean;
  warnings: string[];
  warning_messages: string[];
}

interface WarningAgg {
  code: string;
  severity: string;
  message: string;
  doc_ids: string[];
  primary: boolean;
}

interface AnswerTrustReport {
  citations: CitationTrust[];
  warnings: WarningAgg[];
  has_warnings: boolean;
  severity: string;
  base_confidence: number;
  adjusted_confidence: number;
  confidence_penalty: number;
  min_trust: number;
  relies_on_retracted: boolean;
}

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

async function getReport(url: string): Promise<AnswerTrustReport> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<AnswerTrustReport>;
}

const TIER: Record<string, { ru: string; cls: string }> = {
  high: { ru: 'высокое доверие', cls: 'text-verified border-verified/40' },
  medium: { ru: 'среднее доверие', cls: 'text-gap border-gap/40' },
  low: { ru: 'низкое доверие', cls: 'text-contradiction border-contradiction/40' },
  untrusted: { ru: 'без доверия', cls: 'text-contradiction border-contradiction/50' },
};

const FRESH: Record<string, { ru: string; cls: string }> = {
  fresh: { ru: 'свежий', cls: 'text-verified' },
  aging: { ru: 'стареет', cls: 'text-gap' },
  stale: { ru: 'устарел', cls: 'text-contradiction' },
  unknown: { ru: 'неизвестно', cls: 'text-faint' },
};

const STATUS: Record<string, { ru: string; cls: string }> = {
  active: { ru: 'активен', cls: 'text-verified border-verified/40' },
  corrected: { ru: 'исправлен', cls: 'text-gap border-gap/40' },
  retracted: { ru: 'ОТОЗВАН', cls: 'text-contradiction border-contradiction/50' },
  superseded: { ru: 'заменён', cls: 'text-contradiction border-contradiction/40' },
  deprecated: { ru: 'устарел', cls: 'text-gap border-gap/40' },
};

const SEVERITY_CLS: Record<string, string> = {
  critical: 'border-contradiction/50 bg-contradiction/10 text-contradiction',
  high: 'border-gap/40 bg-gap/10 text-gap',
  medium: 'border-line bg-surface/60 text-muted',
  none: 'border-verified/40 bg-verified/10 text-verified',
};

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function SourceTrustView() {
  // The demo endpoint returns a live active+stale+retracted scenario; a doc_id list
  // could be POSTed to /assess instead once wired into the answer view.
  const [source] = useState<'demo'>('demo');
  const report = useQuery({
    queryKey: ['source-trust', source],
    queryFn: () => getReport('/api/v1/source-trust/demo'),
  });

  const data = report.data;

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col overflow-y-auto p-6">
      <header className="mb-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <ShieldCheck size={16} className="text-copper" /> Доверие к источникам
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-faint">
          отзыв · свежесть · рецензирование — и как это влияет на уверенность ответа
        </div>
      </header>

      {report.isLoading ? (
        <div className="flex items-center gap-2 font-mono text-[12px] text-faint">
          <Loader2 size={14} className="animate-spin text-copper" /> загрузка…
        </div>
      ) : report.isError ? (
        <div className="text-sm text-contradiction">Не удалось загрузить оценку доверия.</div>
      ) : data ? (
        <>
          <ConfidenceCard report={data} />
          <WarningPanel warnings={data.warnings} />
          <CitationTable citations={data.citations} />
        </>
      ) : null}
    </div>
  );
}

function ConfidenceCard({ report }: { report: AnswerTrustReport }) {
  const dropped = report.adjusted_confidence < report.base_confidence;
  return (
    <div className="panel mb-4 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wide text-faint">
          итоговая уверенность ответа
        </div>
        {report.relies_on_retracted && (
          <span className="chip text-contradiction border-contradiction/50">
            <AlertOctagon size={11} /> опора на отозванный источник
          </span>
        )}
      </div>

      <div className="flex items-end gap-4">
        <div>
          <div className="metric text-3xl text-copper">{pct(report.adjusted_confidence)}</div>
          <div className="font-mono text-[10px] text-faint">после учёта доверия</div>
        </div>
        {dropped && (
          <div className="pb-1 text-faint">
            <span className="font-mono text-sm line-through">{pct(report.base_confidence)}</span>
            <span className="ml-2 font-mono text-[11px] text-contradiction">
              −{Math.round((1 - report.confidence_penalty) * 100)}%
            </span>
          </div>
        )}
      </div>

      {/* Base vs adjusted bar */}
      <div className="mt-3 h-2 w-full overflow-hidden rounded bg-surface/60">
        <div
          className="h-full rounded bg-copper transition-all"
          style={{ width: pct(report.adjusted_confidence) }}
        />
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[10px] text-faint">
        <span>мин. доверие источника: {report.min_trust.toFixed(2)}</span>
        <span>штраф ×{report.confidence_penalty.toFixed(2)}</span>
      </div>
    </div>
  );
}

function WarningPanel({ warnings }: { warnings: WarningAgg[] }) {
  if (warnings.length === 0) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-md border border-verified/40 bg-verified/10 px-3 py-2 text-sm text-verified">
        <BadgeCheck size={15} /> Предупреждений по источникам нет.
      </div>
    );
  }
  return (
    <div className="mb-4 space-y-2">
      {warnings.map((w) => (
        <div
          key={w.code}
          className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${
            SEVERITY_CLS[w.severity] ?? SEVERITY_CLS.medium
          }`}
        >
          {w.severity === 'critical' ? (
            <AlertOctagon size={15} className="mt-0.5 shrink-0" />
          ) : (
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          )}
          <div>
            <div>{w.message}</div>
            <div className="mt-0.5 font-mono text-[10px] opacity-80">
              {w.primary ? 'основной источник · ' : ''}
              {w.doc_ids.join(', ')}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CitationTable({ citations }: { citations: CitationTrust[] }) {
  const sorted = useMemo(
    () => [...citations].sort((a, b) => a.trust_score - b.trust_score),
    [citations],
  );
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead>
          <tr className="border-b border-line font-mono text-[10px] uppercase tracking-wide text-faint">
            <th className="px-3 py-2">Источник</th>
            <th className="px-3 py-2">Статус</th>
            <th className="px-3 py-2">Доверие</th>
            <th className="px-3 py-2">Свежесть</th>
            <th className="px-3 py-2">Предупреждения</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => {
            const tier = TIER[c.trust_tier] ?? TIER.low;
            const fresh = FRESH[c.freshness_level] ?? FRESH.unknown;
            const status = STATUS[c.source_status] ?? STATUS.active;
            return (
              <tr key={c.doc_id} className="border-b border-line/60 align-top">
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1.5 text-ink/90">
                    {c.primary && (
                      <span title="основной источник" className="text-copper">
                        <ShieldAlert size={13} />
                      </span>
                    )}
                    <span className="font-mono text-[12px]">{c.doc_id}</span>
                  </div>
                </td>
                <td className="px-3 py-2">
                  <span className={`chip ${status.cls}`}>{status.ru}</span>
                </td>
                <td className="px-3 py-2">
                  <span className={`chip ${tier.cls}`}>{tier.ru}</span>
                  <span className="ml-1.5 font-mono text-[10px] text-faint">
                    {c.trust_score.toFixed(2)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1 text-[12px] ${fresh.cls}`}>
                    <Clock size={11} /> {fresh.ru}
                    {c.age_days != null && (
                      <span className="text-faint">· {Math.round(c.age_days)}д</span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {c.warning_messages.length === 0 ? (
                    <span className="text-faint">—</span>
                  ) : (
                    <ul className="space-y-0.5 text-[11px] text-muted">
                      {c.warning_messages.map((m, i) => (
                        <li key={i} className="flex items-start gap-1">
                          <AlertTriangle size={11} className="mt-0.5 shrink-0 text-gap" />
                          {m}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
