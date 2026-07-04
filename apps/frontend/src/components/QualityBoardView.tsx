import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  BadgeCheck,
  CircleCheck,
  CircleX,
  Gauge,
  Loader2,
  Play,
  Quote,
  Ruler,
  ShieldCheck,
  Sigma,
} from 'lucide-react';

// §13.25 «Живое табло качества» — golden + deterministic answer-quality metrics.
// Self-contained (no api.ts edits): calls the quality-board router directly with the
// same session-auth convention as api.ts / BenchmarkView.

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

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

interface MetricInfo {
  id: string;
  label: string;
  lower_is_better: boolean;
}
interface BoardInfo {
  judge_model: string;
  metrics: MetricInfo[];
  thresholds: Record<string, number>;
  lower_is_better: string[];
  golden_size: number;
  note: string;
}

interface Gate {
  value: number;
  threshold: number;
  passed: boolean;
}
interface CaseRow {
  id: string;
  title: string;
  query: string;
  error?: string;
  n_citations: number;
  citation_precision: number;
  phantom_citations: string[];
  n_claims: number;
  unsupported_claim_rate: number;
  numeric_claims: number;
  numeric_claims_without_evidence: number;
  numeric_accuracy: number | null;
  expected_units: string[];
  answer_units: string[];
  unit_accuracy: number | null;
  expect_contradiction: boolean;
  contradiction_found: boolean;
}
interface BoardResult {
  metrics: Record<string, number>;
  gates: Record<string, Gate>;
  passed: boolean;
  support: Record<string, number>;
  numeric_guardrail_ok: boolean;
  golden_size: number;
  judge_model: string;
  cases: CaseRow[];
  mlflow_run: { run_id?: string } | null;
}

const METRIC_META: Record<string, { label: string; icon: typeof Quote; lower: boolean }> = {
  citation_precision: { label: 'Точность цитирования', icon: Quote, lower: false },
  unsupported_claim_rate: { label: 'Неподтверждённые утв.', icon: AlertTriangle, lower: true },
  numeric_accuracy: { label: 'Точность чисел', icon: Sigma, lower: false },
  unit_accuracy: { label: 'Точность единиц', icon: Ruler, lower: false },
  contradiction_recall: { label: 'Recall противоречий', icon: ShieldCheck, lower: false },
};

const ORDER = [
  'citation_precision',
  'unsupported_claim_rate',
  'numeric_accuracy',
  'unit_accuracy',
  'contradiction_recall',
];

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function MetricCard({ id, gate }: { id: string; gate: Gate }) {
  const meta = METRIC_META[id];
  const Icon = meta?.icon ?? Gauge;
  const good = gate.passed;
  const bar = Math.max(0, Math.min(1, gate.value));
  return (
    <div
      style={{
        border: '1px solid var(--border, #2a2f3a)',
        borderRadius: 12,
        padding: '14px 16px',
        background: 'var(--panel, #171b24)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minWidth: 190,
        flex: '1 1 190px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: 0.85 }}>
        <Icon size={16} />
        <span style={{ fontSize: 13 }}>{meta?.label ?? id}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 26, fontWeight: 700 }}>{pct(gate.value)}</span>
        {good ? (
          <CircleCheck size={18} color="#4ade80" />
        ) : (
          <CircleX size={18} color="#f87171" />
        )}
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 4,
          background: 'var(--track, #2a2f3a)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${bar * 100}%`,
            height: '100%',
            background: good ? '#4ade80' : '#f87171',
          }}
        />
      </div>
      <div style={{ fontSize: 11, opacity: 0.6 }}>
        порог {meta?.lower ? '≤ ' : '≥ '}
        {pct(gate.threshold)}
      </div>
    </div>
  );
}

function fmtOpt(v: number | null): string {
  return v === null ? '—' : pct(v);
}

export function QualityBoardView() {
  const [result, setResult] = useState<BoardResult | null>(null);
  const [useLlm, setUseLlm] = useState(false);

  const info = useQuery({
    queryKey: ['quality-board-info'],
    queryFn: () => apiGet<BoardInfo>('/api/v1/quality-board/info'),
  });

  const run = useMutation({
    mutationFn: () =>
      apiPost<BoardResult>('/api/v1/quality-board/run', {
        use_llm: useLlm,
        log_mlflow: true,
      }),
    onSuccess: setResult,
  });

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <Gauge size={22} />
        <h2 style={{ margin: 0 }}>Живое табло качества</h2>
      </div>
      <p style={{ opacity: 0.7, marginTop: 0, fontSize: 14 }}>
        Мы измеряем собственную точность: golden-набор (§15.1) прогоняется через живого
        агента, метрики §15.2 считаются детерминированно (без LLM-судьи).
      </p>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          flexWrap: 'wrap',
          margin: '12px 0 20px',
        }}
      >
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '9px 16px',
            borderRadius: 8,
            border: 'none',
            background: '#3b82f6',
            color: '#fff',
            cursor: run.isPending ? 'wait' : 'pointer',
            fontSize: 14,
          }}
        >
          {run.isPending ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {run.isPending ? 'Прогон golden…' : 'Прогнать табло'}
        </button>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
          Синтез OSS-LLM (медленнее, реалистичнее)
        </label>
        {info.data && (
          <span style={{ fontSize: 12, opacity: 0.6 }}>
            golden: {info.data.golden_size} вопр. · судья: {info.data.judge_model}
          </span>
        )}
      </div>

      {run.isError && (
        <div style={{ color: '#f87171', marginBottom: 16 }}>
          Ошибка прогона: {(run.error as Error).message}
        </div>
      )}

      {result && (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 14px',
              borderRadius: 10,
              marginBottom: 16,
              background: result.passed ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
              border: `1px solid ${result.passed ? '#4ade80' : '#f87171'}`,
            }}
          >
            {result.passed ? (
              <BadgeCheck size={20} color="#4ade80" />
            ) : (
              <AlertTriangle size={20} color="#f87171" />
            )}
            <strong>{result.passed ? 'Все пороги §15.2 пройдены' : 'Есть метрики ниже порога'}</strong>
            <span style={{ opacity: 0.7, fontSize: 13 }}>
              · guardrail «числовой claim без evidence»:{' '}
              {result.numeric_guardrail_ok ? '0 нарушений' : `${result.support.numeric_claims_without_evidence} наруш.`}
            </span>
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
            {ORDER.filter((id) => result.gates[id]).map((id) => (
              <MetricCard key={id} id={id} gate={result.gates[id]} />
            ))}
          </div>

          <h3 style={{ marginBottom: 8 }}>Разбивка по вопросам golden-набора</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: 'left', opacity: 0.7 }}>
                  <th style={{ padding: '6px 10px' }}>Вопрос</th>
                  <th style={{ padding: '6px 10px' }}>Цитаты</th>
                  <th style={{ padding: '6px 10px' }}>Цит.точн.</th>
                  <th style={{ padding: '6px 10px' }}>Неподтв.</th>
                  <th style={{ padding: '6px 10px' }}>Числа</th>
                  <th style={{ padding: '6px 10px' }}>Единицы</th>
                  <th style={{ padding: '6px 10px' }}>Противоречие</th>
                </tr>
              </thead>
              <tbody>
                {result.cases.map((c) => (
                  <tr key={c.id} style={{ borderTop: '1px solid var(--border, #2a2f3a)' }}>
                    <td style={{ padding: '6px 10px', maxWidth: 320 }}>
                      <div style={{ fontWeight: 600 }}>{c.title || c.id}</div>
                      <div style={{ opacity: 0.55, fontSize: 12 }}>
                        {c.error ? `ошибка: ${c.error}` : c.query.slice(0, 90)}
                      </div>
                    </td>
                    <td style={{ padding: '6px 10px' }}>
                      {c.n_citations}
                      {c.phantom_citations.length > 0 && (
                        <span style={{ color: '#f87171' }}> ({c.phantom_citations.length} фантом)</span>
                      )}
                    </td>
                    <td style={{ padding: '6px 10px' }}>{pct(c.citation_precision)}</td>
                    <td style={{ padding: '6px 10px' }}>{pct(c.unsupported_claim_rate)}</td>
                    <td style={{ padding: '6px 10px' }}>
                      {fmtOpt(c.numeric_accuracy)}
                      {c.numeric_claims_without_evidence > 0 && (
                        <span style={{ color: '#fbbf24' }}> ⚠{c.numeric_claims_without_evidence}</span>
                      )}
                    </td>
                    <td style={{ padding: '6px 10px' }}>{fmtOpt(c.unit_accuracy)}</td>
                    <td style={{ padding: '6px 10px' }}>
                      {c.expect_contradiction ? (
                        c.contradiction_found ? (
                          <CircleCheck size={15} color="#4ade80" />
                        ) : (
                          <CircleX size={15} color="#f87171" />
                        )
                      ) : (
                        <span style={{ opacity: 0.4 }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.mlflow_run?.run_id && (
            <div style={{ marginTop: 14, fontSize: 12, opacity: 0.6 }}>
              MLflow run: {result.mlflow_run.run_id} (эксперимент answer, §15.3)
            </div>
          )}
        </>
      )}

      {info.data && (
        <p style={{ marginTop: 24, fontSize: 12, opacity: 0.55 }}>{info.data.note}</p>
      )}
    </div>
  );
}
