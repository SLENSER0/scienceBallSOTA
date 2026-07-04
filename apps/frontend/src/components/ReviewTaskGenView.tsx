import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  GitCompareArrows,
  Layers,
  Loader2,
  ListChecks,
  Play,
  ScanSearch,
  ShieldQuestion,
  Sparkles,
  Tag,
} from 'lucide-react';

// §16.5 Авто-генерация review-задач по 6 правилам. Self-contained (без правок
// api.ts): дёргает роутер /api/v1/curation/tasks/* напрямую с той же
// session-auth конвенцией, что и api.ts.

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

interface RuleInfo {
  task_type: string;
  title: string;
  type_rank: number;
  target_type: string;
}
interface RulesResponse {
  rules: RuleInfo[];
  defaults: {
    confidence_threshold: number;
    ocr_threshold: number;
    er_margin: number;
    critical_fields: Record<string, string[]>;
  };
  priority_order: string[];
}

interface ReviewTask {
  task_type: string;
  target_type: string;
  target_id: string;
  payload: Record<string, unknown>;
  priority: number;
  dedup_key: string;
}
interface ScanResponse {
  count: number;
  returned: number;
  by_type: Record<string, number>;
  disabled_rules: string[];
  scope: { doc_id: string | null; batch_id: string | null };
  config: { confidence_threshold: number; ocr_threshold: number; er_margin: number };
  elapsed_ms: number;
  tasks: ReviewTask[];
}

const TYPE_META: Record<string, { label: string; icon: typeof Tag; cls: string }> = {
  contradiction: { label: 'Противоречие', icon: GitCompareArrows, cls: 'text-red-400 border-red-500/40' },
  missing_critical_field: {
    label: 'Нет критического поля',
    icon: AlertTriangle,
    cls: 'text-amber-400 border-amber-500/40',
  },
  ambiguous_er: {
    label: 'Неоднозначный ER',
    icon: ShieldQuestion,
    cls: 'text-violet-400 border-violet-500/40',
  },
  low_confidence: { label: 'Низкая уверенность', icon: Layers, cls: 'text-sky-400 border-sky-500/40' },
  low_quality_ocr: { label: 'Низкое качество OCR', icon: ScanSearch, cls: 'text-orange-400 border-orange-500/40' },
  new_schema_term: { label: 'Новый термин схемы', icon: Sparkles, cls: 'text-emerald-400 border-emerald-500/40' },
};

function typeMeta(t: string) {
  return TYPE_META[t] ?? { label: t, icon: Tag, cls: 'text-faint border-white/10' };
}

function TypeBadge({ t }: { t: string }) {
  const m = typeMeta(t);
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${m.cls}`}>
      <Icon size={12} />
      {m.label}
    </span>
  );
}

function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload).filter(([, v]) => v !== null && v !== undefined && v !== '');
  return (
    <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <dt className="shrink-0 text-faint">{k}</dt>
          <dd className="break-all font-mono text-ink/80">
            {typeof v === 'object' ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ReviewTaskGenView() {
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [disabled, setDisabled] = useState<Set<string>>(new Set());
  const [docId, setDocId] = useState('');
  const [confThr, setConfThr] = useState(0.65);
  const [ocrThr, setOcrThr] = useState(0.6);
  const [erMargin, setErMargin] = useState(0.15);

  const rules = useQuery({
    queryKey: ['task-gen-rules'],
    queryFn: () => apiGet<RulesResponse>('/api/v1/curation/tasks/rules'),
  });

  const scan = useMutation({
    mutationFn: () =>
      apiPost<ScanResponse>('/api/v1/curation/tasks/scan', {
        doc_id: docId.trim() || null,
        disabled_rules: [...disabled],
        confidence_threshold: confThr,
        ocr_threshold: ocrThr,
        er_margin: erMargin,
        limit: 300,
      }),
    onSuccess: setResult,
  });

  const toggle = (t: string) =>
    setDisabled((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  const order = rules.data?.priority_order ?? [];
  const byType = result?.by_type ?? {};
  const totalByType = useMemo(
    () => order.reduce((acc, t) => acc + (byType[t] ?? 0), 0),
    [order, byType],
  );

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">Авто-генерация задач курирования · §16.5</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Генератор review-задач (6 правил)</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Очередь курирования наполняется автоматически: шесть правил над живым графом чеканят задачи —
          <span className="text-ink/80"> low_confidence</span>, <span className="text-ink/80">ambiguous_er</span>,
          <span className="text-ink/80"> contradiction</span>, <span className="text-ink/80">missing_critical_field</span>,
          <span className="text-ink/80"> low_quality_ocr</span>, <span className="text-ink/80">new_schema_term</span>.
          Задачи дедуплицируются по <span className="font-mono">dedup_key</span> (повторный прогон не плодит дублей)
          и сортируются по приоритету (§16.4). Отключите любое правило — соответствующие задачи исчезнут.
        </p>

        {/* Rule toggles */}
        <div className="panel mb-4 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
            <ListChecks size={16} /> Правила
          </div>
          <div className="flex flex-wrap gap-2">
            {(rules.data?.rules ?? []).map((r) => {
              const off = disabled.has(r.task_type);
              const m = typeMeta(r.task_type);
              const Icon = m.icon;
              return (
                <button
                  key={r.task_type}
                  onClick={() => toggle(r.task_type)}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition ${
                    off ? 'border-white/10 text-faint line-through opacity-60' : m.cls
                  }`}
                  title={off ? 'Правило выключено' : 'Правило включено · нажмите чтобы выключить'}
                >
                  <Icon size={12} />
                  {r.title}
                  <span className="ml-1 font-mono opacity-70">·{r.type_rank}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Params + run */}
        <div className="panel mb-6 p-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-xs text-faint">
              Порог уверенности · {confThr.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={confThr}
                onChange={(e) => setConfThr(Number(e.target.value))}
                className="mt-1 w-full accent-copper"
              />
            </label>
            <label className="text-xs text-faint">
              Порог OCR · {ocrThr.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={ocrThr}
                onChange={(e) => setOcrThr(Number(e.target.value))}
                className="mt-1 w-full accent-copper"
              />
            </label>
            <label className="text-xs text-faint">
              ER margin · {erMargin.toFixed(2)}
              <input
                type="range"
                min={0}
                max={0.5}
                step={0.01}
                value={erMargin}
                onChange={(e) => setErMargin(Number(e.target.value))}
                className="mt-1 w-full accent-copper"
              />
            </label>
            <label className="text-xs text-faint">
              Scope · doc_id (опц.)
              <input
                type="text"
                value={docId}
                placeholder="весь граф"
                onChange={(e) => setDocId(e.target.value)}
                className="mt-1 w-full rounded border border-white/10 bg-transparent px-2 py-1 text-xs text-ink"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={() => scan.mutate()}
              disabled={scan.isPending}
              className="btn-copper flex items-center gap-2"
            >
              {scan.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {scan.isPending ? 'Сканирование…' : 'Прогнать правила'}
            </button>
            {result && (
              <span className="text-xs text-faint">
                {result.count} задач · показано {result.returned} · {result.elapsed_ms} мс
                {result.scope.doc_id ? ` · doc ${result.scope.doc_id}` : ' · весь граф'}
              </span>
            )}
          </div>
        </div>

        {scan.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка сканирования: {(scan.error as Error).message}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* By-type summary */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {order.map((t) => {
                const m = typeMeta(t);
                const Icon = m.icon;
                const n = byType[t] ?? 0;
                const off = result.disabled_rules.includes(t);
                return (
                  <div
                    key={t}
                    className={`panel p-3 ${off ? 'opacity-50' : ''}`}
                    title={m.label}
                  >
                    <div className={`flex items-center gap-1.5 text-xs ${m.cls.split(' ')[0]}`}>
                      <Icon size={13} />
                      <span className="truncate">{m.label}</span>
                    </div>
                    <div className="mt-1 font-display text-2xl font-semibold text-ink">
                      {off ? '—' : n}
                    </div>
                  </div>
                );
              })}
            </div>

            {totalByType === 0 && (
              <div className="panel p-4 text-sm text-faint">
                Задач не создано — при текущих порогах и данных дефектов не найдено. Поднимите порог
                уверенности или снимите scope, чтобы увидеть больше кандидатов.
              </div>
            )}

            {/* Task list */}
            <div className="space-y-2">
              {result.tasks.map((task) => (
                <div key={task.dedup_key} className="panel p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <TypeBadge t={task.task_type} />
                    <span className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-faint">
                      {task.target_type}
                    </span>
                    <span className="truncate font-mono text-xs text-ink/70">{task.target_id}</span>
                    <span className="ml-auto font-mono text-xs text-copper" title="Приоритет (§16.4)">
                      ▲ {task.priority.toFixed(2)}
                    </span>
                  </div>
                  <PayloadView payload={task.payload} />
                </div>
              ))}
            </div>
          </div>
        )}

        {!result && !scan.isPending && (
          <div className="panel p-4 text-sm text-faint">
            Нажмите «Прогнать правила» — генератор просканирует живой граф и покажет
            дедуплицированную очередь review-задач, отсортированную по приоритету.
          </div>
        )}
      </div>
    </div>
  );
}
