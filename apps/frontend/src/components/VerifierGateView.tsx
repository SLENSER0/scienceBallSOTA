import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowRight,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  TriangleAlert,
  ScanSearch,
  Hash,
  Clock,
  CheckCircle2,
  XCircle,
  FileWarning,
} from 'lucide-react';
import { api } from '../api';

/**
 * §15.8 — Verifier-gate: блокировка неподкреплённых чисел + scan_gaps как tool.
 *
 * Две связанные гарантии evidence-first, показанные вживую:
 *
 * 1. scan_gaps как tool: по контексту вопроса (резолвинг сущностей → 1-hop scope)
 *    тянет открытые :Gap-узлы ABOUT темы ПРЯМО в контекст запроса. Пробелы типа
 *    missing_source_span выделяются — именно они запускают блокирующее правило.
 * 2. Verifier блокирует финализацию: если в ответе есть числовое утверждение без
 *    inline-ссылки [n] И в контексте есть сопутствующий пробел missing_source_span —
 *    ответ НЕ финализируется (blocked). Число без источника + отсутствующий span =
 *    ответ не может выдаваться за проверенный.
 *
 * Backend: POST /api/v1/verifier-gate/verify + /scan-gaps (routers/verifier_gate.py).
 */

export interface GapRow {
  id: string;
  name: string;
  gapType: string;
  subjectId: string;
  subject: string;
}

export interface EntityRow {
  id: string;
  name: string;
  label: string;
  domain?: string | null;
  score: number;
}

export interface ScanContext {
  question?: string;
  tokens: string[];
  entities: EntityRow[];
  scopeIds: string[];
  gaps: GapRow[];
  gapCount: number;
  byType: Record<string, number>;
  missingSourceSpan: GapRow[];
  missingSourceSpanCount: number;
  contextNote?: string;
  tool: {
    name: string;
    status: string;
    durationMs: number;
    error?: string | null;
    resultSize: number;
  };
}

export interface NumericValidation {
  ok: boolean;
  numeric_claims_without_evidence: string[];
  has_citations: boolean;
  issues: string[];
}

export interface VerifyResult {
  question: string;
  answer: string;
  blocked: boolean;
  finalize: boolean;
  verdict: 'blocked' | 'warning' | 'ok';
  blockReason: string | null;
  notes: string[];
  numericValidation: NumericValidation;
  unsupportedCount: number;
  scan: ScanContext;
  contextNote: string;
}

const EXAMPLES: { q: string; a: string }[] = [
  {
    q: 'Твёрдость сплава Al-Cu после старения',
    a: 'После старения при 180 °C твёрдость выросла до 145 HV, что на 40% выше исходной.',
  },
  {
    q: 'Прочность титановых сплавов ВТ6',
    a: 'Предел прочности сплава ВТ6 составляет 950 МПа [1] по данным испытаний.',
  },
];

function VerdictBadge({ verdict }: { verdict: VerifyResult['verdict'] }) {
  if (verdict === 'blocked')
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-gap/15 px-2.5 py-1 text-sm font-semibold text-gap">
        <ShieldX size={16} /> Финализация заблокирована
      </span>
    );
  if (verdict === 'warning')
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-copper/15 px-2.5 py-1 text-sm font-semibold text-copper">
        <ShieldAlert size={16} /> Предупреждение
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-verified/15 px-2.5 py-1 text-sm font-semibold text-verified">
      <ShieldCheck size={16} /> Ответ подкреплён
    </span>
  );
}

function GapChip({ gap, blocking }: { gap: GapRow; blocking?: boolean }) {
  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${
        blocking ? 'border-gap/40 bg-gap/5' : 'border-nickel/25 bg-ink/[0.02]'
      }`}
    >
      <FileWarning
        size={14}
        className={`mt-0.5 shrink-0 ${blocking ? 'text-gap' : 'text-nickel'}`}
      />
      <div className="min-w-0">
        <code
          className={`rounded px-1 text-[10px] font-medium ${
            blocking ? 'bg-gap/10 text-gap' : 'bg-nickel/10 text-nickel'
          }`}
        >
          {gap.gapType}
        </code>
        <p className="mt-0.5 truncate text-muted" title={gap.name}>
          {gap.name || gap.subject || gap.id}
        </p>
      </div>
    </div>
  );
}

export function VerifierGateView() {
  const [q, setQ] = useState('');
  const [answer, setAnswer] = useState('');
  const verify = useMutation({
    mutationFn: (p: { question: string; answer: string }) =>
      api.verifierGate(p.question, p.answer),
  });
  const data = verify.data;

  const submit = () => {
    if (q.trim() && answer.trim()) verify.mutate({ question: q.trim(), answer: answer.trim() });
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow text-copper">§15.8 · Verifier gate</div>
        <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
          Блокировка неподкреплённых чисел
        </h2>
        <p className="mt-1 text-sm text-muted">
          Verifier не финализирует ответ с числом без ссылки <code>[n]</code> при сопутствующем
          пробеле <code>missing_source_span</code>. Инструмент <b>scan_gaps</b> тянет открытые
          пробелы прямо в контекст запроса — сильная гарантия evidence-first.
        </p>

        {/* Composer */}
        <div className="panel mt-4 space-y-2 p-3 shadow-panel">
          <label className="block text-[11px] font-medium uppercase tracking-wide text-faint">
            Вопрос (контекст для scan_gaps)
          </label>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Например: твёрдость сплава Al-Cu после старения"
            className="w-full rounded-md bg-ink/[0.03] px-3 py-2 text-sm text-ink placeholder:text-faint focus:outline-none focus:ring-1 focus:ring-copper/40"
          />
          <label className="block pt-1 text-[11px] font-medium uppercase tracking-wide text-faint">
            Черновик ответа (число без <code>[n]</code> → неподкреплено)
          </label>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={3}
            placeholder="Текст ответа с числами и inline-ссылками [1]…"
            className="w-full resize-none rounded-md bg-ink/[0.03] px-3 py-2 text-sm text-ink placeholder:text-faint focus:outline-none focus:ring-1 focus:ring-copper/40"
          />
          <div className="flex justify-end">
            <button
              onClick={submit}
              disabled={verify.isPending || !q.trim() || !answer.trim()}
              className="btn-copper flex items-center gap-1.5"
            >
              {verify.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              <span>Проверить</span>
            </button>
          </div>
        </div>

        {/* Examples */}
        {!data && !verify.isPending && (
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.q}
                onClick={() => {
                  setQ(ex.q);
                  setAnswer(ex.a);
                  verify.mutate({ question: ex.q, answer: ex.a });
                }}
                className="chip max-w-full text-left text-muted transition-colors hover:text-nickel"
                title={ex.a}
              >
                {ex.q}
              </button>
            ))}
          </div>
        )}

        {verify.isError && (
          <p className="mt-4 rounded-md bg-gap/10 px-3 py-2 text-sm text-gap">
            Не удалось выполнить проверку. Попробуйте другой вопрос/ответ.
          </p>
        )}

        {/* Result */}
        {data && (
          <div className="mt-5 space-y-4">
            {/* Verdict header */}
            <div className="panel p-4 shadow-panel">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <VerdictBadge verdict={data.verdict} />
                <span
                  className={`inline-flex items-center gap-1.5 text-sm font-medium ${
                    data.finalize ? 'text-verified' : 'text-gap'
                  }`}
                >
                  {data.finalize ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                  finalize = {String(data.finalize)}
                </span>
              </div>
              {data.blockReason && (
                <p className="mt-3 rounded-md border border-gap/30 bg-gap/5 px-3 py-2 text-sm text-gap">
                  {data.blockReason}
                </p>
              )}
              <ul className="mt-3 space-y-1.5">
                {data.notes.map((n, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-muted">
                    <TriangleAlert size={13} className="mt-0.5 shrink-0 text-faint" />
                    {n}
                  </li>
                ))}
              </ul>
            </div>

            {/* Numeric validation */}
            <div className="panel p-4 shadow-panel">
              <div className="mb-2 flex items-center gap-2">
                <Hash size={15} className="text-copper" />
                <h3 className="font-display text-sm font-semibold text-ink">
                  §13.12 · Числовые утверждения
                </h3>
                <span
                  className={`ml-auto rounded px-1.5 py-0.5 text-[11px] font-medium ${
                    data.numericValidation.ok
                      ? 'bg-verified/15 text-verified'
                      : 'bg-gap/15 text-gap'
                  }`}
                >
                  {data.numericValidation.ok ? 'все подкреплены' : `без ссылки: ${data.unsupportedCount}`}
                </span>
              </div>
              {data.numericValidation.numeric_claims_without_evidence.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {data.numericValidation.numeric_claims_without_evidence.map((num, i) => (
                    <code
                      key={`${num}-${i}`}
                      className="rounded bg-gap/10 px-1.5 py-0.5 text-xs font-medium text-gap"
                    >
                      {num}
                    </code>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">
                  Каждое число в ответе несёт inline-ссылку <code>[n]</code>.
                </p>
              )}
              {!data.numericValidation.has_citations && (
                <p className="mt-2 text-xs italic text-faint">
                  Цитаты к ответу не приложены — заземлять числа нечем.
                </p>
              )}
            </div>

            {/* scan_gaps tool context */}
            <div className="panel p-4 shadow-panel">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <ScanSearch size={15} className="text-copper" />
                <h3 className="font-display text-sm font-semibold text-ink">
                  §7.4 · scan_gaps (пробелы в контексте запроса)
                </h3>
                <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-faint">
                  <Clock size={10} />
                  {data.scan.tool.durationMs} ms · {data.scan.tool.status}
                </span>
              </div>
              <p className="text-sm text-muted">{data.contextNote}</p>

              {/* resolved entities */}
              {data.scan.entities.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-faint">
                    Сущности контекста ({data.scan.entities.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {data.scan.entities.slice(0, 8).map((e) => (
                      <span
                        key={e.id}
                        className="rounded bg-nickel/10 px-1.5 py-0.5 text-xs text-nickel"
                        title={`${e.label} · ${e.id}`}
                      >
                        {e.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* by-type tally */}
              {Object.keys(data.scan.byType).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {Object.entries(data.scan.byType).map(([t, c]) => (
                    <span
                      key={t}
                      className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                        t === 'missing_source_span'
                          ? 'bg-gap/15 text-gap'
                          : 'bg-ink/5 text-muted'
                      }`}
                    >
                      {t} · {c}
                    </span>
                  ))}
                </div>
              )}

              {/* missing_source_span subset (the blocking trigger) */}
              {data.scan.missingSourceSpan.length > 0 && (
                <div className="mt-3">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-gap">
                    <ShieldX size={12} /> Триггер блокировки · missing_source_span (
                    {data.scan.missingSourceSpanCount})
                  </div>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {data.scan.missingSourceSpan.slice(0, 6).map((g) => (
                      <GapChip key={g.id} gap={g} blocking />
                    ))}
                  </div>
                </div>
              )}

              {/* other gaps */}
              {data.scan.gaps.filter((g) => g.gapType !== 'missing_source_span').length > 0 && (
                <div className="mt-3">
                  <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    Прочие пробелы в контексте
                  </div>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {data.scan.gaps
                      .filter((g) => g.gapType !== 'missing_source_span')
                      .slice(0, 6)
                      .map((g) => (
                        <GapChip key={g.id} gap={g} />
                      ))}
                  </div>
                </div>
              )}

              {data.scan.gapCount === 0 && (
                <p className="mt-2 text-sm text-muted">
                  Открытых пробелов вокруг темы не найдено.
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
