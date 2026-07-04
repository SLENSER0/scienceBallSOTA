import { useState } from 'react';
import {
  AlertOctagon,
  ArrowRight,
  GitCompareArrows,
  Loader2,
  Quote,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { useStore } from '../store';
import type { View } from '../store';

// §17.7 / §5.2.2 — Единый warning panel для ответа агента: агрегирует четыре
// ортогональных сигнала риска (противоречия, низкая уверенность, пробелы данных,
// числа без цитат) в ОДНУ панель с цветовой индикацией severity и переходами к
// деталям. Guardrail (§13.12) уже метит числа без evidence — здесь эти сигналы
// сводятся вместе с contradictions/gaps/low-confidence, чтобы читатель видел все
// риски ответа сразу. Данные строит backend POST /api/v1/warnings/panel.

interface WarningItem {
  title: string;
  detail: string;
  detail_ref: { view: string; anchor: string };
}

interface WarningCategory {
  key: string;
  label_ru: string;
  label_en: string;
  severity: string;
  count: number;
  items: WarningItem[];
}

interface WarningPanel {
  severity: string;
  has_warnings: boolean;
  total: number;
  counts: Record<string, number>;
  categories: WarningCategory[];
}

// ---- self-contained fetch (не трогаем hub api.ts) ------------------------
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

async function fetchPanel(body: Record<string, unknown>): Promise<WarningPanel> {
  const res = await fetch('/api/v1/warnings/panel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<WarningPanel>;
}

// Backend detail_ref.view строки → реальные front-end View id. Бэкенд отдаёт
// 'evidence' для unsupported_claims, но такого экрана нет — уводим на Evidence
// Pack, чтобы «к деталям» не прыгало на пустой экран. Остальные (contradictions,
// entities, gaps) — валидные View как есть.
const DETAIL_VIEW: Record<string, View> = {
  contradictions: 'contradictions',
  entities: 'entities',
  gaps: 'gaps',
  evidence: 'evidencepack',
};

const CATEGORY_META: Record<
  string,
  { icon: typeof TriangleAlert; hint: string }
> = {
  contradictions: { icon: GitCompareArrows, hint: 'литература расходится в значениях' },
  unsupported_claims: { icon: Quote, hint: 'числа в ответе без ссылки на источник' },
  low_confidence: { icon: TriangleAlert, hint: 'факты и цитаты с низкой уверенностью' },
  missing_data: { icon: AlertOctagon, hint: 'нет данных по теме' },
};

// Цвет по severity — critical/high читаются как опасность, medium/low — как предупреждение.
function sevClasses(sev: string): string {
  switch (sev) {
    case 'critical':
      return 'border-rust/50 bg-rust/10 text-rust';
    case 'high':
      return 'border-copper/60 bg-copper/10 text-copper';
    case 'medium':
      return 'border-nickel/40 bg-nickel/10 text-nickel-bright';
    default:
      return 'border-line bg-surface/60 text-muted';
  }
}

function sevLabel(sev: string): string {
  switch (sev) {
    case 'critical':
      return 'критично';
    case 'high':
      return 'высокий риск';
    case 'medium':
      return 'внимание';
    default:
      return 'чисто';
  }
}

export function WarningPanelView() {
  const { answer, role, useLlm, setView } = useStore();
  const [query, setQuery] = useState('');
  const [panel, setPanel] = useState<WarningPanel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(mode: 'answer' | 'query') {
    setLoading(true);
    setError(null);
    setPanel(null);
    try {
      const body: Record<string, unknown> =
        mode === 'answer' && answer
          ? { answer }
          : { query: query.trim(), role, use_llm: useLlm };
      setPanel(await fetchPanel(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const canRunAnswer = Boolean(answer && answer.answerMarkdown);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">панель рисков ответа</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Единая панель предупреждений
        </h2>
        <p className="mb-6 max-w-3xl text-sm text-muted">
          Все риски ответа в одном месте: <b>противоречия</b>, <b>низкая уверенность</b>,{' '}
          <b>пробелы данных</b> и <b>числа без ссылок на источник</b>. Цвет — по
          серьёзности; клик по карточке ведёт к деталям на соответствующем экране.
        </p>

        {/* -- Источник ответа: текущий ответ из «Запроса» или новый вопрос -- */}
        <div className="mb-6 space-y-3 rounded-xl border border-line bg-surface/40 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && query.trim()) run('query');
              }}
              placeholder="Вопрос (напр. «твёрдость Al-Cu после старения 180°C 2ч»)"
              className="min-w-[16rem] flex-1 rounded-lg border border-line bg-base px-3 py-2 text-sm outline-none focus:border-copper/60"
            />
            <button
              onClick={() => run('query')}
              disabled={loading || !query.trim()}
              className="flex items-center gap-1.5 rounded-lg border border-copper/60 bg-copper/10 px-3 py-2 text-sm text-copper disabled:opacity-40"
            >
              {loading ? <Loader2 className="animate-spin" size={15} /> : <ShieldCheck size={15} />}
              Проверить ответ
            </button>
          </div>
          {canRunAnswer && (
            <button
              onClick={() => run('answer')}
              disabled={loading}
              className="text-xs text-muted underline decoration-dotted hover:text-ink"
            >
              …или проверить текущий ответ из экрана «Запрос» (без повторного запроса)
            </button>
          )}
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-rust/40 bg-rust/10 px-3 py-2 text-sm text-rust">
            <TriangleAlert size={16} /> Не удалось построить панель: {error}
          </div>
        )}

        {panel && !panel.has_warnings && (
          <div className="flex items-center gap-2 rounded-lg border border-line bg-surface/60 px-3 py-3 text-sm text-muted">
            <ShieldCheck size={16} /> Рисков не найдено — противоречий, пробелов и чисел без
            цитат нет, уверенность выше порога.
          </div>
        )}

        {panel && panel.has_warnings && (
          <>
            {/* -- Сводная плашка severity + счётчики ------------------------ */}
            <div
              className={`mb-5 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 ${sevClasses(
                panel.severity,
              )}`}
            >
              <TriangleAlert size={18} />
              <span className="font-medium">
                Общий уровень: {sevLabel(panel.severity)} · {panel.total} предупреждений
              </span>
              <span className="ml-auto flex flex-wrap gap-3 text-xs">
                {panel.categories
                  .filter((c) => c.count > 0)
                  .map((c) => (
                    <span key={c.key}>
                      {c.label_ru}: <b>{c.count}</b>
                    </span>
                  ))}
              </span>
            </div>

            {/* -- Категории с items и переходами к деталям ------------------ */}
            <div className="space-y-4">
              {panel.categories
                .filter((c) => c.count > 0)
                .map((c) => {
                  const M = CATEGORY_META[c.key];
                  const Icon = M?.icon ?? TriangleAlert;
                  return (
                    <section
                      key={c.key}
                      className={`rounded-xl border ${sevClasses(c.severity)} bg-surface/40 p-4`}
                    >
                      <header className="mb-2 flex items-center gap-2">
                        <Icon size={16} />
                        <h3 className="font-medium">{c.label_ru}</h3>
                        <span className="rounded-full border border-current px-2 py-0.5 text-xs">
                          {c.count}
                        </span>
                        <span className="ml-auto text-xs opacity-70">{M?.hint}</span>
                      </header>
                      <ul className="space-y-2">
                        {c.items.map((it, i) => (
                          <li
                            key={`${c.key}-${i}`}
                            className="flex items-start gap-3 rounded-lg border border-line bg-base/60 px-3 py-2"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-medium text-ink">
                                {it.title}
                              </div>
                              <div className="text-xs text-muted">{it.detail}</div>
                            </div>
                            <button
                              onClick={() => setView(DETAIL_VIEW[it.detail_ref.view] ?? 'entities')}
                              className="flex shrink-0 items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-muted hover:border-copper/60 hover:text-copper"
                            >
                              к деталям <ArrowRight size={12} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </section>
                  );
                })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
