import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BookMarked,
  CircleCheck,
  CircleSlash,
  Languages,
  Loader2,
  Search,
  Star,
  TriangleAlert,
} from 'lucide-react';

// §18.6 golden QA dataset viewer. Self-contained (no api.ts / types.ts edits):
// calls the golden-dataset router directly with the same session-auth convention
// as api.ts. Read-only surface over the versioned §15.1 corpus + quota gate.

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

const BASE = '/api/v1/golden-dataset';

interface QuotaRow {
  category: string;
  quota: number;
  count: number;
  met: boolean;
  surplus: number;
}
interface Summary {
  manifest: { dataset_version: string; name: string; description: string; git_tag: string | null };
  total: number;
  ok: boolean;
  reference_present: boolean;
  reference_id: string;
  quota: QuotaRow[];
  languages: Record<string, number>;
  warnings: string[];
  schema_errors: string[];
  duplicate_ids: string[];
}
interface QuestionRow {
  id: string;
  category: string;
  language: string;
  question: string;
  has_numeric: boolean;
  has_citations: boolean;
  n_entities: number;
  n_gaps: number;
  n_contradictions: number;
  tags: string[];
}
interface QuestionsResponse {
  total_matched: number;
  returned: number;
  questions: QuestionRow[];
}
interface QuestionDetail extends QuestionRow {
  expected_entities: { material: string[]; processing: string[]; property: string[] };
  expected_answer_contains: string[];
  must_not_contain: string[];
  required_graph_nodes: string[];
  expected_numeric: { quantity: string | null; value: number; unit: string; tolerance: number } | null;
  expected_citations: { evidence_ids: string[]; doc_ids: string[] };
  expected_gaps: string[];
  expected_contradictions: string[];
}

const CATEGORY_LABELS: Record<string, string> = {
  material_regime_property: 'Материал/режим/свойство',
  experiment_lookup: 'Поиск эксперимента',
  evidence: 'Доказательства',
  gap: 'Пробелы',
  contradiction: 'Противоречия',
  broad_summary: 'Обзор литературы',
};

function Pill({ text, tone }: { text: string; tone: 'ok' | 'warn' | 'muted' }) {
  const cls =
    tone === 'ok'
      ? 'bg-emerald-500/15 text-emerald-500'
      : tone === 'warn'
        ? 'bg-amber-500/15 text-amber-500'
        : 'bg-slate-500/15 text-slate-400';
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{text}</span>;
}

export function GoldenDatasetView() {
  const [category, setCategory] = useState<string>('');
  const [language, setLanguage] = useState<string>('');
  const [q, setQ] = useState<string>('');
  const [openId, setOpenId] = useState<string | null>(null);

  const summary = useQuery({
    queryKey: ['golden-summary'],
    queryFn: () => apiGet<Summary>(`${BASE}/summary`),
  });

  const list = useQuery({
    queryKey: ['golden-questions', category, language, q],
    queryFn: () => {
      const p = new URLSearchParams();
      if (category) p.set('category', category);
      if (language) p.set('language', language);
      if (q.trim()) p.set('q', q.trim());
      p.set('limit', '500');
      return apiGet<QuestionsResponse>(`${BASE}/questions?${p.toString()}`);
    },
  });

  const detail = useQuery({
    queryKey: ['golden-detail', openId],
    queryFn: () => apiGet<QuestionDetail>(`${BASE}/questions/${openId}`),
    enabled: openId != null,
  });

  const s = summary.data;
  const langBadges = useMemo(
    () => (s ? Object.entries(s.languages) : []),
    [s],
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex items-center gap-3">
        <BookMarked className="h-6 w-6 text-indigo-400" />
        <div>
          <h1 className="text-xl font-semibold">Golden dataset (§18.6)</h1>
          <p className="text-sm text-slate-400">
            Эталонный QA-корпус §15.1 — фундамент метрик доверия и gate «0 unsupported claims».
          </p>
        </div>
      </header>

      {summary.isLoading && (
        <div className="flex items-center gap-2 text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Загрузка сводки…
        </div>
      )}
      {summary.isError && (
        <div className="flex items-center gap-2 rounded border border-rose-500/40 bg-rose-500/10 p-3 text-rose-400">
          <TriangleAlert className="h-4 w-4" /> {(summary.error as Error).message}
        </div>
      )}

      {s && (
        <section className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-slate-700 p-4">
            <div className="text-xs uppercase text-slate-500">Валидатор</div>
            <div className="mt-1 flex items-center gap-2 text-lg font-semibold">
              {s.ok ? (
                <>
                  <CircleCheck className="h-5 w-5 text-emerald-500" /> Набор валиден
                </>
              ) : (
                <>
                  <CircleSlash className="h-5 w-5 text-rose-500" /> Есть нарушения
                </>
              )}
            </div>
            <div className="mt-2 text-sm text-slate-400">
              Вопросов: <span className="font-semibold text-slate-200">{s.total}</span>
            </div>
          </div>

          <div className="rounded-lg border border-slate-700 p-4">
            <div className="text-xs uppercase text-slate-500">Версия / манифест</div>
            <div className="mt-1 text-lg font-semibold">{s.manifest.dataset_version}</div>
            <div className="mt-1 text-sm text-slate-400">{s.manifest.name}</div>
            {s.manifest.git_tag && (
              <div className="mt-1 text-xs text-slate-500">tag: {s.manifest.git_tag}</div>
            )}
          </div>

          <div className="rounded-lg border border-slate-700 p-4">
            <div className="text-xs uppercase text-slate-500">Языки / эталон</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Languages className="h-4 w-4 text-slate-400" />
              {langBadges.map(([lang, n]) => (
                <Pill key={lang} tone="muted" text={`${lang}: ${n}`} />
              ))}
            </div>
            <div className="mt-2 flex items-center gap-2 text-sm">
              <Star className={`h-4 w-4 ${s.reference_present ? 'text-amber-400' : 'text-rose-500'}`} />
              <span className="text-slate-400">
                Al-Cu эталон: {s.reference_present ? 'присутствует' : 'ОТСУТСТВУЕТ'}
              </span>
            </div>
          </div>
        </section>
      )}

      {s && (
        <section className="rounded-lg border border-slate-700 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase text-slate-400">
            Покрытие квот §15.1
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="pb-2">Категория</th>
                  <th className="pb-2 text-right">Квота</th>
                  <th className="pb-2 text-right">Факт</th>
                  <th className="pb-2 text-right">Статус</th>
                </tr>
              </thead>
              <tbody>
                {s.quota.map((r) => (
                  <tr key={r.category} className="border-t border-slate-800">
                    <td className="py-1.5">{CATEGORY_LABELS[r.category] ?? r.category}</td>
                    <td className="py-1.5 text-right text-slate-400">{r.quota}</td>
                    <td className="py-1.5 text-right font-semibold">{r.count}</td>
                    <td className="py-1.5 text-right">
                      {r.met ? (
                        <Pill tone="ok" text={r.surplus ? `+${r.surplus}` : 'ok'} />
                      ) : (
                        <Pill tone="warn" text={`не хватает ${r.quota - r.count}`} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(s.warnings.length > 0 || s.schema_errors.length > 0 || s.duplicate_ids.length > 0) && (
            <div className="mt-3 space-y-1 text-xs text-amber-400">
              {s.schema_errors.map((w) => (
                <div key={`e-${w}`}>schema: {w}</div>
              ))}
              {s.duplicate_ids.map((w) => (
                <div key={`d-${w}`}>duplicate id: {w}</div>
              ))}
              {s.warnings.map((w) => (
                <div key={`w-${w}`}>warn: {w}</div>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded border border-slate-700 px-2">
            <Search className="h-4 w-4 text-slate-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Поиск по тексту вопроса…"
              className="bg-transparent py-1.5 text-sm outline-none"
            />
          </div>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded border border-slate-700 bg-transparent px-2 py-1.5 text-sm"
          >
            <option value="">Все категории</option>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded border border-slate-700 bg-transparent px-2 py-1.5 text-sm"
          >
            <option value="">Все языки</option>
            <option value="ru">ru</option>
            <option value="en">en</option>
          </select>
          {list.data && (
            <span className="text-sm text-slate-500">найдено: {list.data.total_matched}</span>
          )}
        </div>

        {list.isLoading && (
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Загрузка вопросов…
          </div>
        )}

        <div className="space-y-2">
          {list.data?.questions.map((item) => (
            <div key={item.id} className="rounded-lg border border-slate-700">
              <button
                onClick={() => setOpenId(openId === item.id ? null : item.id)}
                className="flex w-full items-start justify-between gap-3 p-3 text-left hover:bg-slate-800/40"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill tone="muted" text={item.language} />
                    <span className="text-xs text-slate-500">
                      {CATEGORY_LABELS[item.category] ?? item.category}
                    </span>
                    {item.id === s?.reference_id && (
                      <Star className="h-3.5 w-3.5 text-amber-400" />
                    )}
                  </div>
                  <div className="mt-1 truncate text-sm text-slate-200">{item.question}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {item.has_numeric && <Pill tone="ok" text="num" />}
                  {item.has_citations && <Pill tone="ok" text="cite" />}
                </div>
              </button>

              {openId === item.id && (
                <div className="border-t border-slate-800 p-3 text-sm">
                  {detail.isLoading && (
                    <div className="flex items-center gap-2 text-slate-400">
                      <Loader2 className="h-4 w-4 animate-spin" /> …
                    </div>
                  )}
                  {detail.data && detail.data.id === item.id && (
                    <div className="grid gap-3 md:grid-cols-2">
                      <Field label="Ожидаемые сущности">
                        {[
                          ...detail.data.expected_entities.material,
                          ...detail.data.expected_entities.processing,
                          ...detail.data.expected_entities.property,
                        ].join(', ') || '—'}
                      </Field>
                      <Field label="Ответ содержит">
                        {detail.data.expected_answer_contains.join(', ') || '—'}
                      </Field>
                      <Field label="Не должен содержать">
                        {detail.data.must_not_contain.join(', ') || '—'}
                      </Field>
                      <Field label="Узлы графа">
                        {detail.data.required_graph_nodes.join(', ') || '—'}
                      </Field>
                      {detail.data.expected_numeric && (
                        <Field label="Ожидаемое число">
                          {detail.data.expected_numeric.quantity ?? 'value'}:{' '}
                          {detail.data.expected_numeric.value} {detail.data.expected_numeric.unit}{' '}
                          (±{detail.data.expected_numeric.tolerance})
                        </Field>
                      )}
                      <Field label="Цитаты">
                        {[
                          ...detail.data.expected_citations.evidence_ids,
                          ...detail.data.expected_citations.doc_ids,
                        ].join(', ') || '—'}
                      </Field>
                      {detail.data.expected_gaps.length > 0 && (
                        <Field label="Пробелы">{detail.data.expected_gaps.join(', ')}</Field>
                      )}
                      {detail.data.expected_contradictions.length > 0 && (
                        <Field label="Противоречия">
                          {detail.data.expected_contradictions.join(', ')}
                        </Field>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className="mt-0.5 text-slate-200">{children}</div>
    </div>
  );
}
