import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  BadgeCheck,
  Database,
  FileText,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Terminal,
} from 'lucide-react';

// §3.6 — Панель целостности графа: Cypher-валидатор evidence-first инварианта.
// Одна метрика доказывает на всём корпусе «0 фактов без Evidence / без id /
// без schema_version» через новый бэкенд GET /api/v1/graph-integrity/report:
// по каждой проверке — число нарушителей, доля покрытия, примеры и сам текст
// Cypher (аргумент доверия на демо: инвариант проверяем, а не декларативен).
//
// Self-contained fetch (читает session-токен как api.ts), чтобы не править
// общие hub-файлы; замените на api.graphIntegrity() после проводки метода.

interface IntegrityCheck {
  key: string;
  title: string;
  invariant: string;
  denominator: number;
  violations: number;
  passed: boolean;
  coverage: number;
  cypher: string;
  samples: { id: string; label: string }[];
}

interface IntegrityReport {
  profile: string;
  generated_at: string;
  ok: boolean;
  headline: string;
  total_nodes: number;
  total_facts: number;
  total_evidence: number;
  total_violations: number;
  factual_labels: string[];
  evidence_rels: string[];
  checks: IntegrityCheck[];
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

async function getReport(url: string): Promise<IntegrityReport> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<IntegrityReport>;
}

function pct(x: number): string {
  return `${(x * 100).toFixed(x >= 0.9995 ? 0 : 2)}%`;
}

export function GraphIntegrityView() {
  const report = useQuery({
    queryKey: ['graph-integrity'],
    queryFn: () => getReport('/api/v1/graph-integrity/report'),
  });
  const data = report.data;

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col overflow-y-auto p-6">
      <header className="mb-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <ShieldCheck size={16} className="text-copper" /> Целостность графа
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-faint">
          Cypher-валидатор «0 фактов без Evidence / без id / без schema_version» на всём корпусе
          (§3.6)
        </div>
      </header>

      {report.isLoading ? (
        <div className="flex items-center gap-2 font-mono text-[12px] text-faint">
          <Loader2 size={14} className="animate-spin text-copper" /> прогон Cypher-валидаторов…
        </div>
      ) : report.isError ? (
        <div className="text-sm text-contradiction">
          Не удалось прогнать валидатор целостности графа.
        </div>
      ) : data ? (
        <>
          <Verdict data={data} />
          <CensusStrip data={data} />
          <div className="mt-4 flex flex-col gap-3">
            {data.checks.map((c) => (
              <CheckCard key={c.key} check={c} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

function Verdict({ data }: { data: IntegrityReport }) {
  const ok = data.ok;
  return (
    <div
      className={`panel flex items-start gap-3 border p-4 ${
        ok ? 'border-verified/40 bg-verified/5' : 'border-contradiction/50 bg-contradiction/5'
      }`}
    >
      <div
        className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
          ok ? 'bg-verified/15 text-verified' : 'bg-contradiction/15 text-contradiction'
        }`}
      >
        {ok ? <BadgeCheck size={22} /> : <ShieldAlert size={22} />}
      </div>
      <div className="min-w-0">
        <div className={`text-lg font-semibold ${ok ? 'text-verified' : 'text-contradiction'}`}>
          {ok ? 'Инвариант evidence-first держится' : 'Найдены нарушения инварианта'}
        </div>
        <div className="mt-0.5 text-sm text-nickel">{data.headline}</div>
        <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10px] text-faint">
          <span className="chip border-line">профиль: {data.profile}</span>
          <span className="chip border-line">
            нарушений всего: {data.total_violations.toLocaleString('ru-RU')}
          </span>
          <span className="chip border-line">
            {new Date(data.generated_at).toLocaleString('ru-RU')}
          </span>
        </div>
      </div>
    </div>
  );
}

function CensusStrip({ data }: { data: IntegrityReport }) {
  const cells: { icon: typeof Database; label: string; value: number }[] = [
    { icon: Database, label: 'узлов', value: data.total_nodes },
    { icon: FileText, label: 'фактов', value: data.total_facts },
    { icon: ShieldCheck, label: 'Evidence', value: data.total_evidence },
  ];
  return (
    <div className="mt-3 grid grid-cols-3 gap-3">
      {cells.map((c) => (
        <div key={c.label} className="panel flex flex-col items-center p-3">
          <c.icon size={15} className="text-copper" />
          <div className="metric mt-1 text-2xl leading-none text-nickel">
            {c.value.toLocaleString('ru-RU')}
          </div>
          <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-faint">
            {c.label}
          </div>
        </div>
      ))}
    </div>
  );
}

function CheckCard({ check }: { check: IntegrityCheck }) {
  const ok = check.passed;
  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {ok ? (
              <ShieldCheck size={16} className="text-verified" />
            ) : (
              <AlertTriangle size={16} className="text-contradiction" />
            )}
            <span className="font-medium text-nickel">{check.title}</span>
          </div>
          <div className="mt-0.5 text-[12px] text-faint">{check.invariant}</div>
        </div>
        <div
          className={`chip shrink-0 ${
            ok
              ? 'border-verified/40 text-verified'
              : 'border-contradiction/50 text-contradiction'
          }`}
        >
          {check.violations === 0
            ? '0 нарушений'
            : `${check.violations.toLocaleString('ru-RU')} нарушений`}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded bg-surface/60">
          <div
            className={`h-full rounded transition-all ${ok ? 'bg-verified' : 'bg-contradiction'}`}
            style={{ width: `${Math.max(2, Math.round(check.coverage * 100))}%` }}
          />
        </div>
        <span className="font-mono text-[11px] text-faint">
          покрытие {pct(check.coverage)} · база {check.denominator.toLocaleString('ru-RU')}
        </span>
      </div>

      <details className="mt-3 group">
        <summary className="flex cursor-pointer items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint hover:text-nickel">
          <Terminal size={12} /> Cypher-запрос
        </summary>
        <pre className="mt-2 overflow-x-auto rounded border border-line bg-surface/40 p-2.5 font-mono text-[11px] leading-relaxed text-nickel">
          {check.cypher}
        </pre>
      </details>

      {check.samples.length > 0 ? (
        <div className="mt-2">
          <div className="font-mono text-[10px] uppercase tracking-wide text-contradiction">
            примеры-нарушители
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {check.samples.map((s) => (
              <span
                key={s.id}
                className="chip border-contradiction/40 font-mono text-[10px] text-nickel"
                title={s.id}
              >
                {s.label || 'Node'}:{s.id.length > 22 ? `${s.id.slice(0, 22)}…` : s.id}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
