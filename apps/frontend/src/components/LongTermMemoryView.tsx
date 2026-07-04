import { useCallback, useEffect, useState } from 'react';
import {
  Brain,
  Loader2,
  Trash2,
  Plus,
  Sparkles,
  Tag,
  SlidersHorizontal,
  Star,
  RefreshCw,
} from 'lucide-react';

// §13.20 — Кросс-сессионная долговременная память (персонализация).
// Ассистент помнит между сессиями подтверждённые алиасы сущностей, предпочтения и
// часто используемые фильтры (namespace (user_id, "memories"), backend
// /api/v1/memory). Экран показывает память пользователя, позволяет добавить/забыть
// факт и «примерить» персонализацию к новому запросу (алиасы + фильтры-по-умолчанию).

interface MemoryRecord {
  key: string;
  kind: string;
  value: Record<string, unknown>;
  created_at: number;
  ttl_s: number | null;
  expired: boolean;
}
interface MemoryListResponse {
  user_id: string;
  namespace: string[];
  count: number;
  max_items: number;
  counts_by_kind: Record<string, number>;
  records: MemoryRecord[];
}
interface PersonalizeResponse {
  user_id: string;
  mentions: string[];
  filters: Record<string, unknown>;
  applied: string[];
  memory_used: number;
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

async function apiGet(userId: string): Promise<MemoryListResponse> {
  const res = await fetch(`/api/v1/memory/${encodeURIComponent(userId)}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<MemoryListResponse>;
}

async function apiPut(userId: string, body: Record<string, unknown>): Promise<void> {
  const res = await fetch(`/api/v1/memory/${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${(await res.text()) || res.statusText}`);
}

async function apiDelete(userId: string, key: string): Promise<void> {
  const res = await fetch(
    `/api/v1/memory/${encodeURIComponent(userId)}/${key.split('/').map(encodeURIComponent).join('/')}`,
    { method: 'DELETE', headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

async function apiPersonalize(
  userId: string,
  mentions: string[],
  filters: Record<string, unknown>,
): Promise<PersonalizeResponse> {
  const res = await fetch(`/api/v1/memory/${encodeURIComponent(userId)}/personalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ mentions, filters }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<PersonalizeResponse>;
}

const KIND_META: Record<string, { label: string; icon: typeof Tag }> = {
  alias: { label: 'Алиас сущности', icon: Tag },
  preference: { label: 'Предпочтение', icon: Star },
  frequent_filter: { label: 'Частый фильтр', icon: SlidersHorizontal },
};

function KindBadge({ kind }: { kind: string }) {
  const meta = KIND_META[kind] ?? { label: kind, icon: Tag };
  const Icon = meta.icon;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-copper/40 bg-copper/10 px-2 py-0.5 text-[11px] text-copper">
      <Icon className="h-3 w-3" />
      {meta.label}
    </span>
  );
}

function summarizeValue(rec: MemoryRecord): string {
  if (rec.kind === 'alias') return `${rec.value.mention} → ${rec.value.canonical}`;
  if (rec.kind === 'preference') return `${rec.value.key} = ${JSON.stringify(rec.value.value)}`;
  if (rec.kind === 'frequent_filter') return JSON.stringify(rec.value.filter);
  return JSON.stringify(rec.value);
}

export function LongTermMemoryView() {
  const [userId, setUserId] = useState('analyst');
  const [data, setData] = useState<MemoryListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // add-form state
  const [kind, setKind] = useState<'alias' | 'preference' | 'frequent_filter'>('alias');
  const [mention, setMention] = useState('');
  const [canonical, setCanonical] = useState('');
  const [prefKey, setPrefKey] = useState('');
  const [prefValue, setPrefValue] = useState('');
  const [filterJson, setFilterJson] = useState('{"domain": "metallurgy"}');
  const [saving, setSaving] = useState(false);

  // personalize tester state
  const [pMentions, setPMentions] = useState('');
  const [pFilters, setPFilters] = useState('{}');
  const [pResult, setPResult] = useState<PersonalizeResponse | null>(null);
  const [pError, setPError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await apiGet(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = async () => {
    setSaving(true);
    setError(null);
    try {
      let body: Record<string, unknown>;
      if (kind === 'alias') body = { kind, mention, canonical };
      else if (kind === 'preference') body = { kind, key: prefKey, value: prefValue };
      else body = { kind, filter: JSON.parse(filterJson) };
      await apiPut(userId, body);
      setMention('');
      setCanonical('');
      setPrefKey('');
      setPrefValue('');
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (key: string) => {
    try {
      await apiDelete(userId, key);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const runPersonalize = async () => {
    setPError(null);
    try {
      const mentions = pMentions.split(',').map((s) => s.trim()).filter(Boolean);
      const filters = pFilters.trim() ? JSON.parse(pFilters) : {};
      setPResult(await apiPersonalize(userId, mentions, filters));
    } catch (e) {
      setPError(e instanceof Error ? e.message : String(e));
      setPResult(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-lg font-semibold text-nickel">
          <Brain className="h-5 w-5 text-copper" />
          Долговременная память ассистента
        </h1>
        <p className="text-sm text-muted">
          §13.20 — персонализация между сессиями. Подтверждённые алиасы, предпочтения и частые
          фильтры хранятся в namespace <code className="text-copper">(user_id, "memories")</code> и
          применяются к новому запросу до разрешения сущностей.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Пользователь (user_id)
          <input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="w-56 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 text-sm text-nickel"
          />
        </label>
        <button
          onClick={() => void refresh()}
          className="flex items-center gap-1.5 rounded-md border border-line bg-surface/40 px-3 py-1.5 text-sm text-muted hover:border-copper/40 hover:text-nickel"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Обновить
        </button>
        {data && (
          <span className="text-xs text-muted">
            {data.count} / {data.max_items} записей ·{' '}
            {Object.entries(data.counts_by_kind)
              .map(([k, v]) => `${KIND_META[k]?.label ?? k}: ${v}`)
              .join(' · ') || 'пусто'}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Memory list */}
      <section className="space-y-2">
        <h2 className="text-sm font-medium text-nickel">Что помнит ассистент</h2>
        {data && data.records.length === 0 && (
          <p className="rounded-md border border-line bg-surface/30 px-3 py-4 text-sm text-muted">
            Память пуста. Добавьте факт ниже или дайте агенту подтвердить сущности в диалоге.
          </p>
        )}
        <ul className="space-y-2">
          {data?.records.map((rec) => (
            <li
              key={rec.key}
              className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface/40 px-3 py-2"
            >
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex items-center gap-2">
                  <KindBadge kind={rec.kind} />
                  {rec.ttl_s != null && (
                    <span className="text-[11px] text-muted">TTL {rec.ttl_s}s</span>
                  )}
                </div>
                <span className="truncate text-sm text-nickel" title={summarizeValue(rec)}>
                  {summarizeValue(rec)}
                </span>
              </div>
              <button
                onClick={() => void remove(rec.key)}
                title="Забыть"
                className="shrink-0 rounded-md border border-line p-1.5 text-muted hover:border-red-500/50 hover:text-red-300"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* Add form */}
      <section className="space-y-3 rounded-md border border-line bg-surface/30 p-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-nickel">
          <Plus className="h-4 w-4 text-copper" />
          Запомнить факт
        </h2>
        <div className="flex flex-wrap gap-2">
          {(['alias', 'preference', 'frequent_filter'] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={
                'rounded-md border px-2.5 py-1 text-xs transition ' +
                (kind === k
                  ? 'border-copper/60 bg-copper/15 text-copper'
                  : 'border-line bg-surface/40 text-muted hover:text-nickel')
              }
            >
              {KIND_META[k].label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {kind === 'alias' && (
            <>
              <input
                placeholder="упоминание (напр. AA2024)"
                value={mention}
                onChange={(e) => setMention(e.target.value)}
                className="w-52 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 text-sm text-nickel"
              />
              <input
                placeholder="канонический id (напр. MAT:al-cu-2024)"
                value={canonical}
                onChange={(e) => setCanonical(e.target.value)}
                className="w-64 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 text-sm text-nickel"
              />
            </>
          )}
          {kind === 'preference' && (
            <>
              <input
                placeholder="ключ (напр. lang)"
                value={prefKey}
                onChange={(e) => setPrefKey(e.target.value)}
                className="w-52 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 text-sm text-nickel"
              />
              <input
                placeholder="значение (напр. ru)"
                value={prefValue}
                onChange={(e) => setPrefValue(e.target.value)}
                className="w-52 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 text-sm text-nickel"
              />
            </>
          )}
          {kind === 'frequent_filter' && (
            <input
              placeholder='{"domain": "metallurgy"}'
              value={filterJson}
              onChange={(e) => setFilterJson(e.target.value)}
              className="w-96 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 font-mono text-sm text-nickel"
            />
          )}
          <button
            onClick={() => void add()}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-md border border-copper/60 bg-copper/15 px-3 py-1.5 text-sm text-copper hover:bg-copper/25 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Запомнить
          </button>
        </div>
      </section>

      {/* Personalize tester */}
      <section className="space-y-3 rounded-md border border-line bg-surface/30 p-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-nickel">
          <Sparkles className="h-4 w-4 text-copper" />
          Примерить персонализацию к запросу
        </h2>
        <p className="text-xs text-muted">
          Так память подхватывается в следующей сессии: упоминания переписываются на канонические
          id, частые фильтры добавляются как значения по умолчанию (не перекрывая явные).
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Упоминания (через запятую)
            <input
              placeholder="AA2024, Cu"
              value={pMentions}
              onChange={(e) => setPMentions(e.target.value)}
              className="w-64 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 text-sm text-nickel"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            Явные фильтры (JSON)
            <input
              placeholder="{}"
              value={pFilters}
              onChange={(e) => setPFilters(e.target.value)}
              className="w-64 rounded-md border border-line bg-surface/40 px-2.5 py-1.5 font-mono text-sm text-nickel"
            />
          </label>
          <button
            onClick={() => void runPersonalize()}
            className="flex items-center gap-1.5 rounded-md border border-copper/60 bg-copper/15 px-3 py-1.5 text-sm text-copper hover:bg-copper/25"
          >
            <Sparkles className="h-4 w-4" />
            Применить память
          </button>
        </div>
        {pError && <div className="text-sm text-red-300">{pError}</div>}
        {pResult && (
          <div className="space-y-2 rounded-md border border-line bg-surface/50 p-3 text-sm">
            <div>
              <span className="text-muted">Упоминания → </span>
              <span className="font-mono text-nickel">{JSON.stringify(pResult.mentions)}</span>
            </div>
            <div>
              <span className="text-muted">Фильтры → </span>
              <span className="font-mono text-nickel">{JSON.stringify(pResult.filters)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted">Применено:</span>
              {pResult.applied.length ? (
                pResult.applied.map((a) => (
                  <span
                    key={a}
                    className="rounded-full border border-copper/40 bg-copper/10 px-2 py-0.5 text-[11px] text-copper"
                  >
                    {a === 'alias' ? 'алиасы' : a === 'filter' ? 'фильтры' : a}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-muted">ничего (память не совпала)</span>
              )}
              <span className="ml-auto text-[11px] text-muted">
                использовано записей: {pResult.memory_used}
              </span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
