import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  CircleCheck,
  FlaskConical,
  Loader2,
  Send,
  ShieldCheck,
  ThumbsUp,
  TriangleAlert,
} from 'lucide-react';

// §23.22 Expert feedback loop. Self-contained (no api.ts / hub edits): calls the
// expert-feedback router directly with the same session-auth convention as api.ts.
// Эксперт помечает ответ useful / wrong-number / missing-evidence → фидбэк
// сохраняется и КАЖДАЯ ошибка замораживается в regression-кейс для §18.11.

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
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = String(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

type FbType =
  | 'useful'
  | 'not_useful'
  | 'wrong_number'
  | 'missing_evidence'
  | 'bad_graph'
  | 'bad_entity_match';

interface FeedbackEvent {
  id: string;
  type: FbType;
  question: string;
  answer?: string;
  run_id?: string;
  evidence_id?: string;
  note?: string;
  role?: string;
  user?: string;
  created_at: string;
  wrong_value?: string;
  correct_value?: string;
  expected_evidence?: string;
}

interface EventsResponse {
  total: number;
  count: number;
  events: FeedbackEvent[];
}

interface RegressionCaseDto {
  case_id: string;
  question: string;
  expected_substrings: string[];
  forbidden_substrings: string[];
  category: string;
  source_feedback_id: string;
}

interface CasesResponse {
  count: number;
  cases: RegressionCaseDto[];
}

interface StatsResponse {
  total: number;
  useful: number;
  errors: number;
  useful_rate: number;
  trust_score: number;
  by_type: Record<string, number>;
  regression_set_size: number;
  avg_time_to_evidence_ms: number | null;
  avg_clicks_to_verify: number | null;
  acceptance: {
    min_reviews: number;
    min_useful_rate: number;
    reviews_ok: boolean;
    useful_rate_ok: boolean;
    met: boolean;
  };
}

interface SubmitResponse {
  event: FeedbackEvent;
  regression_case: RegressionCaseDto | null;
  created_regression_case: boolean;
  regression_set_size: number;
}

const TYPE_LABEL: Record<FbType, string> = {
  useful: 'полезный',
  not_useful: 'бесполезный',
  wrong_number: 'неверное число',
  missing_evidence: 'нет доказательства',
  bad_graph: 'плохой граф',
  bad_entity_match: 'плохое сопоставление',
};

const CATEGORY_LABEL: Record<string, string> = {
  numeric_accuracy: 'точность чисел',
  evidence_required: 'нужны доказательства',
  general: 'общее',
};

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

export function ExpertFeedbackView() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [runId, setRunId] = useState('');
  const [evidenceId, setEvidenceId] = useState('');
  const [wrongValue, setWrongValue] = useState('');
  const [correctValue, setCorrectValue] = useState('');
  const [expectedEvidence, setExpectedEvidence] = useState('');
  const [note, setNote] = useState('');
  const [lastCaseId, setLastCaseId] = useState<string | null>(null);

  const stats = useQuery({
    queryKey: ['expert-fb-stats'],
    queryFn: () => apiGet<StatsResponse>('/api/v1/expert-feedback/stats'),
  });
  const events = useQuery({
    queryKey: ['expert-fb-events'],
    queryFn: () => apiGet<EventsResponse>('/api/v1/expert-feedback/events?limit=25'),
  });
  const cases = useQuery({
    queryKey: ['expert-fb-cases'],
    queryFn: () => apiGet<CasesResponse>('/api/v1/expert-feedback/cases'),
  });

  const refetchAll = () => {
    stats.refetch();
    events.refetch();
    cases.refetch();
  };

  const submit = useMutation({
    mutationFn: (type: FbType) =>
      apiPost<SubmitResponse>('/api/v1/expert-feedback/submit', {
        type,
        question: question.trim(),
        answer,
        run_id: runId,
        evidence_id: evidenceId,
        wrong_value: wrongValue,
        correct_value: correctValue,
        expected_evidence: expectedEvidence,
        note,
      }),
    onSuccess: (d) => {
      setLastCaseId(d.regression_case?.case_id ?? null);
      refetchAll();
    },
  });

  const questionOk = question.trim().length > 0;
  const wrongNumberOk = questionOk && wrongValue.trim() !== '' && correctValue.trim() !== '';

  const s = stats.data;
  const acc = s?.acceptance;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">Expert feedback loop · §23.22</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Экспертная оценка ответов → regression-набор
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Эксперт помечает ответ агента как полезный, с неверным числом или без
          доказательства. Каждое событие сохраняется с привязкой к run/evidence
          (provenance §3.7), а каждая ошибка замораживается в детерминированный
          regression-кейс и попадает в набор для gate качества §18.11. Так реальная
          экспертная ошибка превращается в regression-тест.
        </p>

        {/* Acceptance / trust scorecard */}
        {s && acc && (
          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="panel p-3">
              <div className="text-xs text-faint">Оценено ответов</div>
              <div className="mt-1 font-display text-2xl text-ink">{s.total}</div>
              <div className={`text-xs ${acc.reviews_ok ? 'text-emerald-400' : 'text-amber-400'}`}>
                цель ≥ {acc.min_reviews}
              </div>
            </div>
            <div className="panel p-3">
              <div className="text-xs text-faint">Trust score (useful)</div>
              <div className="mt-1 font-display text-2xl text-ink">{pct(s.trust_score)}</div>
              <div
                className={`text-xs ${acc.useful_rate_ok ? 'text-emerald-400' : 'text-amber-400'}`}
              >
                цель ≥ {pct(acc.min_useful_rate)}
              </div>
            </div>
            <div className="panel p-3">
              <div className="text-xs text-faint">Regression-кейсов</div>
              <div className="mt-1 font-display text-2xl text-ink">{s.regression_set_size}</div>
              <div className="text-xs text-faint">из {s.errors} ошибок</div>
            </div>
            <div
              className={`panel p-3 ${acc.met ? 'border-emerald-500/40' : 'border-amber-500/40'}`}
            >
              <div className="text-xs text-faint">Критерий §23.22</div>
              <div className="mt-1 flex items-center gap-2 font-display text-lg text-ink">
                {acc.met ? (
                  <CircleCheck size={20} className="text-emerald-400" />
                ) : (
                  <TriangleAlert size={20} className="text-amber-400" />
                )}
                {acc.met ? 'выполнен' : 'в процессе'}
              </div>
              {s.avg_clicks_to_verify != null && (
                <div className="text-xs text-faint">
                  ~{s.avg_clicks_to_verify} кликов до проверки
                </div>
              )}
            </div>
          </div>
        )}

        {/* Feedback form */}
        <div className="panel mb-6 p-4">
          <h3 className="mb-3 font-display text-lg">Оценить ответ</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block text-xs text-faint">Вопрос *</span>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Что спрашивали у агента"
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block text-xs text-faint">Ответ (опционально)</span>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={2}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-faint">run_id (provenance)</span>
              <input
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 font-mono text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-faint">evidence_id (provenance)</span>
              <input
                value={evidenceId}
                onChange={(e) => setEvidenceId(e.target.value)}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 font-mono text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-faint">Неверное число (для wrong-number)</span>
              <input
                value={wrongValue}
                onChange={(e) => setWrongValue(e.target.value)}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 font-mono text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-faint">Правильное число</span>
              <input
                value={correctValue}
                onChange={(e) => setCorrectValue(e.target.value)}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 font-mono text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block text-xs text-faint">
                Ожидаемое доказательство (для missing-evidence)
              </span>
              <input
                value={expectedEvidence}
                onChange={(e) => setExpectedEvidence(e.target.value)}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 text-sm text-ink outline-none focus:border-copper"
              />
            </label>
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block text-xs text-faint">Замечание эксперта</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full rounded border border-line/60 bg-transparent px-3 py-2 text-sm text-ink outline-none focus:border-copper"
              />
            </label>
          </div>

          {/* Verdict buttons */}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={() => submit.mutate('useful')}
              disabled={!questionOk || submit.isPending}
              className="btn-copper flex items-center gap-2 disabled:opacity-40"
            >
              <ThumbsUp size={16} /> Полезный
            </button>
            <button
              onClick={() => submit.mutate('wrong_number')}
              disabled={!wrongNumberOk || submit.isPending}
              className="flex items-center gap-2 rounded border border-amber-500/50 px-4 py-2 text-sm text-amber-300 hover:bg-amber-500/10 disabled:opacity-40"
              title="Требует неверное и правильное число"
            >
              <TriangleAlert size={16} /> Неверное число
            </button>
            <button
              onClick={() => submit.mutate('missing_evidence')}
              disabled={!questionOk || submit.isPending}
              className="flex items-center gap-2 rounded border border-red-500/50 px-4 py-2 text-sm text-red-300 hover:bg-red-500/10 disabled:opacity-40"
            >
              <ShieldCheck size={16} /> Нет доказательства
            </button>
            {submit.isPending && <Loader2 size={18} className="animate-spin text-faint" />}
          </div>

          {submit.isError && (
            <div className="mt-3 text-sm text-red-400">
              Ошибка: {(submit.error as Error).message}
            </div>
          )}
          {submit.isSuccess && (
            <div className="mt-3 flex items-center gap-2 text-sm text-emerald-400">
              <Send size={15} />
              Фидбэк записан
              {lastCaseId ? (
                <span>
                  · заморожен regression-кейс{' '}
                  <span className="font-mono text-copper">{lastCaseId}</span> (набор:{' '}
                  {submit.data.regression_set_size})
                </span>
              ) : (
                <span>· положительная оценка, кейс не создаётся</span>
              )}
            </div>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Regression case set */}
          <div>
            <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
              <FlaskConical size={18} className="text-copper" />
              Regression-набор для §18.11
              <span className="text-sm text-faint">({cases.data?.count ?? 0})</span>
            </h3>
            <div className="panel divide-y divide-line/30 p-0">
              {(cases.data?.cases ?? []).length === 0 && (
                <div className="p-4 text-sm text-faint">
                  Пока нет замороженных кейсов — отметьте ошибку выше.
                </div>
              )}
              {(cases.data?.cases ?? []).map((c) => (
                <div key={c.case_id} className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-copper">{c.case_id}</span>
                    <span className="rounded bg-line/20 px-2 py-0.5 text-xs text-faint">
                      {CATEGORY_LABEL[c.category] ?? c.category}
                    </span>
                  </div>
                  <div className="mt-1 text-sm text-ink">{c.question}</div>
                  {c.expected_substrings.length > 0 && (
                    <div className="mt-1 text-xs text-emerald-400">
                      должен содержать: {c.expected_substrings.join(', ')}
                    </div>
                  )}
                  {c.forbidden_substrings.length > 0 && (
                    <div className="text-xs text-red-400">
                      не должен содержать: {c.forbidden_substrings.join(', ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Recent events feed */}
          <div>
            <h3 className="mb-2 font-display text-lg">
              Лента фидбэка{' '}
              <span className="text-sm text-faint">({events.data?.total ?? 0})</span>
            </h3>
            <div className="panel divide-y divide-line/30 p-0">
              {(events.data?.events ?? []).length === 0 && (
                <div className="p-4 text-sm text-faint">Событий пока нет.</div>
              )}
              {(events.data?.events ?? []).map((ev) => (
                <div key={ev.id} className="flex items-start gap-3 p-3">
                  <span
                    className={`mt-0.5 rounded px-2 py-0.5 text-xs ${
                      ev.type === 'useful'
                        ? 'bg-emerald-500/15 text-emerald-300'
                        : ev.type === 'wrong_number'
                          ? 'bg-amber-500/15 text-amber-300'
                          : 'bg-red-500/15 text-red-300'
                    }`}
                  >
                    {TYPE_LABEL[ev.type] ?? ev.type}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-ink">{ev.question}</div>
                    <div className="text-xs text-faint">
                      {ev.created_at}
                      {ev.role ? ` · ${ev.role}` : ''}
                      {ev.run_id ? ` · run ${ev.run_id}` : ''}
                      {ev.type === 'wrong_number' && ev.wrong_value
                        ? ` · ${ev.wrong_value} → ${ev.correct_value ?? ''}`
                        : ''}
                    </div>
                    {ev.note && <div className="mt-0.5 text-xs text-faint">«{ev.note}»</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
