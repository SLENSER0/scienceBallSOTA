import { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Languages, Check, Loader2, AlertTriangle, RefreshCw } from 'lucide-react';

// §23.8 — i18n ru/en фронтенда с переключателем локали, синхронизированным с
// языком ответов агента. Бэкенд /api/v1/i18n — единый источник UI-словаря:
//  · GET  /locales       — поддерживаемые локали;
//  · GET  /catalog       — плоский словарь key→string (фолбэк на en);
//  · GET  /completeness  — покрытие переводов + отсутствующие ключи (CI-gate);
//  · PUT  /me/locale     — смена локали, синхронно пишет ui_locale И language
//                          (язык ответов агента) в me/settings.
// Переключение локали здесь меняет строки предпросмотра, формат чисел/дат (Intl)
// и — через me/locale — язык последующих ответов агента, а выбор персистится.

type LocaleCode = 'ru' | 'en';

interface LocaleInfo {
  code: string;
  native: string;
  english: string;
  agent_language: string;
}
interface LocalesResponse {
  default: string;
  fallback: string;
  locales: LocaleInfo[];
}
interface CatalogResponse {
  locale: string;
  agent_language: string;
  count: number;
  fallback_keys: string[];
  messages: Record<string, string>;
}
interface PerLocaleStat {
  total: number;
  covered: number;
  missing_count: number;
  coverage: number;
  missing_keys: string[];
  ok: boolean;
}
interface CompletenessResponse {
  ok: boolean;
  total_keys: number;
  locales: Record<string, PerLocaleStat>;
}
interface MyLocaleResponse {
  user: string;
  locale: string;
  agent_language: string;
  language: string;
}

const LS_KEY = 'sb.uiLocale';

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

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function putLocale(locale: LocaleCode): Promise<MyLocaleResponse> {
  const res = await fetch('/api/v1/i18n/me/locale', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ locale }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<MyLocaleResponse>;
}

// Locale-зависимое форматирование через Intl (§23.8): числа, единицы, даты.
function formatSamples(locale: LocaleCode) {
  const tag = locale === 'ru' ? 'ru-RU' : 'en-US';
  const now = new Date();
  return {
    number: new Intl.NumberFormat(tag).format(1234567.89),
    temperature: new Intl.NumberFormat(tag, { maximumFractionDigits: 1 }).format(1650.5) + ' °C',
    date: new Intl.DateTimeFormat(tag, { dateStyle: 'long', timeStyle: 'short' }).format(now),
    percent: new Intl.NumberFormat(tag, { style: 'percent', maximumFractionDigits: 1 }).format(0.874),
  };
}

// Порядок групп ключей в предпросмотре словаря.
const GROUP_ORDER = ['app', 'nav', 'screen', 'action', 'tab', 'state', 'error', 'format'];

function groupOf(key: string): string {
  const p = key.split('.')[0];
  return GROUP_ORDER.includes(p) ? p : 'other';
}

export function LocaleSwitcherView() {
  const qc = useQueryClient();
  const [locale, setLocale] = useState<LocaleCode>(() => {
    const stored = localStorage.getItem(LS_KEY);
    return stored === 'en' ? 'en' : 'ru';
  });

  const localesQ = useQuery({
    queryKey: ['i18n', 'locales'],
    queryFn: () => getJson<LocalesResponse>('/api/v1/i18n/locales'),
  });
  const catalogQ = useQuery({
    queryKey: ['i18n', 'catalog', locale],
    queryFn: () => getJson<CatalogResponse>(`/api/v1/i18n/catalog?locale=${locale}`),
  });
  const compareQ = useQuery({
    queryKey: ['i18n', 'catalog', locale === 'ru' ? 'en' : 'ru'],
    queryFn: () => getJson<CatalogResponse>(`/api/v1/i18n/catalog?locale=${locale === 'ru' ? 'en' : 'ru'}`),
  });
  const completenessQ = useQuery({
    queryKey: ['i18n', 'completeness'],
    queryFn: () => getJson<CompletenessResponse>('/api/v1/i18n/completeness'),
  });
  const myLocaleQ = useQuery({
    queryKey: ['i18n', 'me', 'locale'],
    queryFn: () => getJson<MyLocaleResponse>('/api/v1/i18n/me/locale'),
  });

  // Инициализация локали из персистированных настроек пользователя (§14.15).
  useEffect(() => {
    const persisted = myLocaleQ.data?.locale;
    if (persisted === 'ru' || persisted === 'en') {
      setLocale(persisted);
      localStorage.setItem(LS_KEY, persisted);
    }
  }, [myLocaleQ.data?.locale]);

  const mutate = useMutation({
    mutationFn: putLocale,
    onSuccess: (data) => {
      const code = data.locale === 'en' ? 'en' : 'ru';
      setLocale(code);
      localStorage.setItem(LS_KEY, code);
      qc.invalidateQueries({ queryKey: ['i18n', 'me', 'locale'] });
    },
  });

  const t = (key: string): string => catalogQ.data?.messages[key] ?? key;
  const samples = useMemo(() => formatSamples(locale), [locale]);

  const rows = useMemo(() => {
    const cur = catalogQ.data?.messages ?? {};
    const other = compareQ.data?.messages ?? {};
    const otherCode = locale === 'ru' ? 'en' : 'ru';
    const keys = Object.keys(cur).sort(
      (a, b) => GROUP_ORDER.indexOf(groupOf(a)) - GROUP_ORDER.indexOf(groupOf(b)) || a.localeCompare(b),
    );
    return { keys, cur, other, otherCode };
  }, [catalogQ.data, compareQ.data, locale]);

  const comp = completenessQ.data;
  const localeList = localesQ.data?.locales ?? [
    { code: 'ru', native: 'Русский', english: 'Russian', agent_language: 'ru' },
    { code: 'en', native: 'English', english: 'English', agent_language: 'en' },
  ];

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-nickel">
            <Languages className="h-5 w-5 text-copper" />
            <h1 className="text-lg font-semibold">{t('format.locale_switcher')}</h1>
          </div>
          <p className="mt-1 text-sm text-muted">{t('format.sync_note')} · §23.8</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-line bg-surface/40 p-1">
          {localeList.map((loc) => {
            const active = loc.code === locale;
            const busy = mutate.isPending && mutate.variables === loc.code;
            return (
              <button
                key={loc.code}
                onClick={() => mutate.mutate(loc.code as LocaleCode)}
                disabled={mutate.isPending}
                className={
                  'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ' +
                  (active
                    ? 'bg-copper/20 text-copper'
                    : 'text-muted hover:bg-surface hover:text-nickel')
                }
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : active ? <Check className="h-3.5 w-3.5" /> : null}
                <span className="uppercase">{loc.code}</span>
                <span className="text-xs opacity-70">{loc.native}</span>
              </button>
            );
          })}
        </div>
      </header>

      {mutate.isError && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          <AlertTriangle className="h-4 w-4" /> {t('error.generic')}
        </div>
      )}

      {/* Синхрон с языком агента + персист */}
      <section className="mb-6 grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-line bg-surface/30 p-4">
          <div className="text-xs uppercase tracking-wide text-muted">Язык ответов агента · language (§7.3)</div>
          <div className="mt-1 flex items-center gap-2 text-nickel">
            <span className="text-xl font-semibold uppercase">{myLocaleQ.data?.language ?? locale}</span>
            <span className="text-sm text-muted">
              {myLocaleQ.isFetching ? 'обновление…' : 'персист в me/settings'}
            </span>
          </div>
          <p className="mt-2 text-xs text-muted">
            Переключатель UI пишет <code className="text-copper">ui_locale</code> и{' '}
            <code className="text-copper">language</code> одним кодом — последующие ответы приходят на этом языке.
          </p>
        </div>

        {/* Intl-форматирование, зависящее от локали */}
        <div className="rounded-lg border border-line bg-surface/30 p-4">
          <div className="text-xs uppercase tracking-wide text-muted">Форматирование (Intl · {locale})</div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted">{t('format.number_example_label')}</dt>
            <dd className="text-nickel tabular-nums">{samples.number}</dd>
            <dt className="text-muted">Temperature</dt>
            <dd className="text-nickel tabular-nums">{samples.temperature}</dd>
            <dt className="text-muted">%</dt>
            <dd className="text-nickel tabular-nums">{samples.percent}</dd>
            <dt className="text-muted">{t('format.date_example_label')}</dt>
            <dd className="text-nickel">{samples.date}</dd>
          </dl>
        </div>
      </section>

      {/* Полнота переводов (i18n-gate §23.8) */}
      <section className="mb-6 rounded-lg border border-line bg-surface/30 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-xs uppercase tracking-wide text-muted">Полнота переводов · i18n-gate</div>
          <button
            onClick={() => completenessQ.refetch()}
            className="flex items-center gap-1 text-xs text-muted hover:text-copper"
          >
            <RefreshCw className="h-3 w-3" /> {t('action.retry')}
          </button>
        </div>
        {comp ? (
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={
                'rounded-md px-2 py-0.5 text-xs font-semibold ' +
                (comp.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300')
              }
            >
              {comp.ok ? 'PASS · нет пропущенных ключей' : 'FAIL · есть пропуски'}
            </span>
            <span className="text-sm text-muted">{comp.total_keys} ключей</span>
            {Object.entries(comp.locales).map(([code, s]) => (
              <span key={code} className="text-sm text-nickel">
                <span className="uppercase text-muted">{code}</span> {(s.coverage * 100).toFixed(0)}%
                {s.missing_count > 0 && <span className="ml-1 text-amber-300">(−{s.missing_count})</span>}
              </span>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted">{t('state.loading')}</div>
        )}
      </section>

      {/* Словарь ru↔en бок о бок — доказательство отсутствия хардкода */}
      <section className="rounded-lg border border-line bg-surface/30">
        <div className="border-b border-line px-4 py-2 text-xs uppercase tracking-wide text-muted">
          Каталог UI-строк ({catalogQ.data?.count ?? 0} ключей) · активная слева
        </div>
        {catalogQ.isLoading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> {t('state.loading')}
          </div>
        ) : rows.keys.length === 0 ? (
          <div className="px-4 py-6 text-sm text-muted">{t('state.empty')}</div>
        ) : (
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface/80 text-xs uppercase text-muted backdrop-blur">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">key</th>
                  <th className="px-4 py-2 text-left font-medium">{locale}</th>
                  <th className="px-4 py-2 text-left font-medium">{rows.otherCode}</th>
                </tr>
              </thead>
              <tbody>
                {rows.keys.map((k) => (
                  <tr key={k} className="border-t border-line/60">
                    <td className="px-4 py-1.5 font-mono text-xs text-copper/80">{k}</td>
                    <td className="px-4 py-1.5 text-nickel">{rows.cur[k]}</td>
                    <td className="px-4 py-1.5 text-muted">{rows.other[k] ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
