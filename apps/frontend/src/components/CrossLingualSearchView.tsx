import { useMemo, useState } from 'react';
import { useQuery, useMutation, keepPreviousData } from '@tanstack/react-query';
import { Languages, Loader2, Search, ArrowRightLeft, ScanText, FlaskConical } from 'lucide-react';

// §23.17 — Устойчивость к ru/«грязным» документам: детект языка + ru→en
// cross-lingual поиск. Бэкенд /api/v1/crosslingual/* использует мультиязычную
// эмбеддинг-модель (granite-embedding-*-multilingual-r2), поэтому ru-запрос
// находит en-контент в одном вектор-пространстве без перевода. Три режима:
//   • Поиск   — cross-lingual семантический поиск по узлам живого графа;
//   • Детект  — язык (ru/en/mixed) + OCR-шум для произвольных чанков;
//   • Recall  — воспроизводимая демонстрация recall@k на «грязном» ru-тексте.

type Lang = 'ru' | 'en' | 'mixed' | 'unknown';

interface NoiseInfo {
  words: number;
  mixed_script_words: number;
  mixed_word_ratio: number;
  junk_ratio: number;
  dirty: boolean;
}
interface SearchHit {
  id: string;
  name: string;
  label: string;
  domain: string | null;
  language: Lang;
  cross_lingual: boolean;
  similarity: number;
  snippet: string;
}
interface SearchResponse {
  query: string;
  query_language: Lang;
  count: number;
  cross_lingual_hits: number;
  hits: SearchHit[];
  took_ms: number;
}
interface DetectResult {
  text: string;
  language: Lang;
  noise: NoiseInfo;
}
interface DetectResponse {
  count: number;
  by_language: Record<string, number>;
  results: DetectResult[];
}
interface DemoCase {
  id: string;
  query: string;
  query_language: Lang;
  noise: NoiseInfo;
  target_en: string;
  found_top1: string;
  'hit@1': boolean;
  'hit@3': boolean;
  similarity_to_target: number;
}
interface DemoLeg {
  recall_at_1: number;
  recall_at_3: number;
  mean_similarity: number;
  cases: DemoCase[];
}
interface DemoResponse {
  pairs: number;
  noise_level: number;
  seed: number;
  embedding_model: string;
  direction: string;
  clean: DemoLeg;
  dirty: DemoLeg;
  degradation: { recall_at_1: number; recall_at_3: number; mean_similarity: number };
}
interface StatusResponse {
  available: boolean;
  embedding_model: string;
  multilingual: boolean;
  nodes_indexed: number;
  nodes_by_language: Record<string, number>;
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

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

const LANG_META: Record<Lang, { label: string; cls: string }> = {
  ru: { label: 'RU', cls: 'border-copper/40 bg-copper/10 text-copper' },
  en: { label: 'EN', cls: 'border-verified/40 bg-verified/10 text-verified' },
  mixed: { label: 'MIX', cls: 'border-contradiction/40 bg-contradiction/10 text-contradiction' },
  unknown: { label: '—', cls: 'border-line text-faint' },
};

function LangBadge({ lang }: { lang: Lang }) {
  const m = LANG_META[lang] ?? LANG_META.unknown;
  return (
    <span className={`chip shrink-0 border text-[9px] ${m.cls}`}>{m.label}</span>
  );
}

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

// --------------------------------------------------------------------------- //
// Tab: cross-lingual search over the live graph                               //
// --------------------------------------------------------------------------- //
function SearchTab() {
  const [input, setInput] = useState('флотация медных руд');
  const [query, setQuery] = useState('флотация медных руд');
  const [onlyLang, setOnlyLang] = useState<'' | Lang>('');

  const q = useQuery<SearchResponse>({
    queryKey: ['xl-search', query, onlyLang],
    queryFn: () =>
      postJSON<SearchResponse>('/api/v1/crosslingual/search', {
        query,
        k: 12,
        only_lang: onlyLang || null,
      }),
    enabled: query.trim().length > 0,
    placeholderData: keepPreviousData,
  });
  const data = q.data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <form
        className="flex flex-wrap items-center gap-2 border-b border-line px-6 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(input.trim());
        }}
      >
        <div className="relative min-w-[220px] flex-1">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="запрос на любом языке — ru найдёт en и наоборот…"
            className="w-full rounded-md border border-line bg-surface/60 py-2 pl-8 pr-3 text-sm text-nickel placeholder:text-faint focus:border-copper/50 focus:outline-none"
          />
        </div>
        <select
          value={onlyLang}
          onChange={(e) => setOnlyLang(e.target.value as '' | Lang)}
          className="rounded-md border border-line bg-surface/60 px-2 py-2 text-xs text-nickel focus:border-copper/50 focus:outline-none"
        >
          <option value="">все языки хитов</option>
          <option value="en">только EN-хиты</option>
          <option value="ru">только RU-хиты</option>
          <option value="mixed">только MIX-хиты</option>
        </select>
        <button
          type="submit"
          className="inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-2 text-xs text-copper transition hover:bg-copper/20"
        >
          <Search size={13} /> Найти
        </button>
      </form>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {data && (
          <div className="mb-3 flex flex-wrap items-center gap-3 font-mono text-[10px] text-faint">
            <span className="inline-flex items-center gap-1">
              язык запроса: <LangBadge lang={data.query_language} />
            </span>
            <span className="inline-flex items-center gap-1 text-copper">
              <ArrowRightLeft size={11} /> cross-lingual попаданий: {data.cross_lingual_hits}/
              {data.count}
            </span>
            <span className="ml-auto">{data.took_ms} мс</span>
          </div>
        )}

        {q.isLoading && !data ? (
          <div className="flex items-center gap-2 font-mono text-[10px] text-faint">
            <Loader2 size={12} className="animate-spin text-copper" /> поиск…
          </div>
        ) : q.isError ? (
          <div className="text-sm text-contradiction">Не удалось выполнить поиск.</div>
        ) : (data?.hits.length ?? 0) === 0 ? (
          <div className="mt-10 text-center font-mono text-xs text-faint">
            ничего не найдено — измените запрос
          </div>
        ) : (
          <div className="grid gap-2">
            {data!.hits.map((h) => (
              <div key={h.id} className="panel p-3">
                <div className="flex items-center gap-2">
                  <LangBadge lang={h.language} />
                  <span className="min-w-0 flex-1 truncate text-sm text-nickel">{h.name}</span>
                  {h.cross_lingual && (
                    <span className="chip shrink-0 border-copper/40 bg-copper/10 text-[9px] text-copper">
                      cross-lingual
                    </span>
                  )}
                  <span className="chip shrink-0 border-line text-[9px] text-faint">{h.label}</span>
                  <span className="shrink-0 font-mono text-[10px] text-copper">
                    {h.similarity.toFixed(3)}
                  </span>
                </div>
                <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
                  {h.snippet}
                </div>
                {h.domain && (
                  <div className="mt-1 font-mono text-[10px] text-faint">{h.domain}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Tab: language + OCR-noise detection                                         //
// --------------------------------------------------------------------------- //
const DETECT_SAMPLE = [
  'Флотация сульфидных медных руд с ксантогенатом в качестве собирателя',
  'Froth flotation of sulfide copper ores using xanthate collector',
  'Флоtаця cyльфидых meдных pуд с ксahтогеhатом',
  'старение Al-Cu alloy повышает yield strength',
].join('\n');

function DetectTab() {
  const [text, setText] = useState(DETECT_SAMPLE);
  const mut = useMutation<DetectResponse, Error, string[]>({
    mutationFn: (texts) => postJSON<DetectResponse>('/api/v1/crosslingual/detect', { texts }),
  });

  const run = () => {
    const lines = text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length) mut.mutate(lines);
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
            чанки / строки (по одной на строку)
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="min-h-0 flex-1 resize-none rounded-md border border-line bg-surface/60 p-3 text-xs leading-relaxed text-nickel placeholder:text-faint focus:border-copper/50 focus:outline-none"
          />
          <button
            onClick={run}
            className="mt-2 inline-flex items-center gap-1.5 self-start rounded-md border border-copper/40 bg-copper/10 px-3 py-1.5 text-xs text-copper transition hover:bg-copper/20"
          >
            <ScanText size={13} /> Детектировать
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto">
          {mut.isPending ? (
            <div className="flex items-center gap-2 font-mono text-[10px] text-faint">
              <Loader2 size={12} className="animate-spin text-copper" /> анализ…
            </div>
          ) : mut.isError ? (
            <div className="text-sm text-contradiction">Ошибка детекции.</div>
          ) : mut.data ? (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2 font-mono text-[10px] text-faint">
                {Object.entries(mut.data.by_language).map(([k, v]) => (
                  <span key={k} className="chip border-line text-faint">
                    {k}: {v}
                  </span>
                ))}
              </div>
              {mut.data.results.map((r, i) => (
                <div key={i} className="panel p-3">
                  <div className="flex items-center gap-2">
                    <LangBadge lang={r.language} />
                    <span className="min-w-0 flex-1 truncate text-xs text-nickel">{r.text}</span>
                    {r.noise.dirty && (
                      <span className="chip shrink-0 border-contradiction/40 bg-contradiction/10 text-[9px] text-contradiction">
                        грязный
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-2 font-mono text-[10px] text-faint">
                    <span>слов: {r.noise.words}</span>
                    <span>homoglyph-слов: {r.noise.mixed_script_words}</span>
                    <span>смешение: {pct(r.noise.mixed_word_ratio)}</span>
                    <span>мусор: {pct(r.noise.junk_ratio)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-10 text-center font-mono text-xs text-faint">
              нажмите «Детектировать»
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Tab: recall on dirty OCR ru-text (parallel corpus)                          //
// --------------------------------------------------------------------------- //
function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="panel px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-wide text-faint">{label}</div>
      <div className={`mt-0.5 font-mono text-lg ${tone ?? 'text-nickel'}`}>{value}</div>
    </div>
  );
}

function DemoTab() {
  const [noise, setNoise] = useState(0.15);
  const [applied, setApplied] = useState(0.15);
  const q = useQuery<DemoResponse>({
    queryKey: ['xl-demo', applied],
    queryFn: () => getJSON<DemoResponse>(`/api/v1/crosslingual/demo?noise=${applied}`),
    placeholderData: keepPreviousData,
  });
  const d = q.data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-6 py-3">
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="font-mono text-[10px] uppercase tracking-wide text-faint">
            OCR-шум запроса
          </span>
          <input
            type="range"
            min={0}
            max={0.5}
            step={0.05}
            value={noise}
            onChange={(e) => setNoise(Number(e.target.value))}
            className="accent-copper"
          />
          <span className="font-mono text-xs text-copper">{pct(noise)}</span>
        </div>
        <button
          onClick={() => setApplied(noise)}
          className="inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-1.5 text-xs text-copper transition hover:bg-copper/20"
        >
          <FlaskConical size={13} /> Прогнать
        </button>
        {d && (
          <span className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] text-faint">
            <ArrowRightLeft size={11} className="text-copper" /> {d.direction}
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {q.isLoading && !d ? (
          <div className="flex items-center gap-2 font-mono text-[10px] text-faint">
            <Loader2 size={12} className="animate-spin text-copper" /> прогон recall…
          </div>
        ) : q.isError ? (
          <div className="text-sm text-contradiction">Не удалось запустить демо.</div>
        ) : d ? (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <Metric label="recall@1 чистый" value={pct(d.clean.recall_at_1)} tone="text-verified" />
              <Metric label="recall@3 чистый" value={pct(d.clean.recall_at_3)} tone="text-verified" />
              <Metric label="ср. cos чистый" value={d.clean.mean_similarity.toFixed(3)} />
              <Metric label="recall@1 грязный" value={pct(d.dirty.recall_at_1)} tone="text-copper" />
              <Metric label="recall@3 грязный" value={pct(d.dirty.recall_at_3)} tone="text-copper" />
              <Metric label="ср. cos грязный" value={d.dirty.mean_similarity.toFixed(3)} />
            </div>
            <div className="mt-2 font-mono text-[10px] text-faint">
              деградация под OCR-шумом: recall@1 −{pct(d.degradation.recall_at_1)} · recall@3 −
              {pct(d.degradation.recall_at_3)} · cos −{d.degradation.mean_similarity.toFixed(3)} ·
              модель {d.embedding_model}
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-xs">
                <thead>
                  <tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-wide text-faint">
                    <th className="py-1.5 pr-3">грязный ru-запрос (OCR)</th>
                    <th className="py-1.5 pr-3">язык</th>
                    <th className="py-1.5 pr-3">найденный en-таргет</th>
                    <th className="py-1.5 pr-3">@1</th>
                    <th className="py-1.5 pr-3">@3</th>
                    <th className="py-1.5 pr-3">cos→таргет</th>
                  </tr>
                </thead>
                <tbody>
                  {d.dirty.cases.map((c) => (
                    <tr key={c.id} className="border-b border-line/50 align-top">
                      <td className="py-1.5 pr-3 text-muted">{c.query}</td>
                      <td className="py-1.5 pr-3">
                        <LangBadge lang={c.query_language} />
                      </td>
                      <td className="py-1.5 pr-3 text-nickel">{c.target_en}</td>
                      <td className="py-1.5 pr-3">
                        <span className={c['hit@1'] ? 'text-verified' : 'text-contradiction'}>
                          {c['hit@1'] ? '✓' : '✗'}
                        </span>
                      </td>
                      <td className="py-1.5 pr-3">
                        <span className={c['hit@3'] ? 'text-verified' : 'text-contradiction'}>
                          {c['hit@3'] ? '✓' : '✗'}
                        </span>
                      </td>
                      <td className="py-1.5 pr-3 font-mono text-copper">
                        {c.similarity_to_target.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Shell                                                                        //
// --------------------------------------------------------------------------- //
type Tab = 'search' | 'detect' | 'demo';

export function CrossLingualSearchView() {
  const [tab, setTab] = useState<Tab>('search');
  const status = useQuery<StatusResponse>({
    queryKey: ['xl-status'],
    queryFn: () => getJSON<StatusResponse>('/api/v1/crosslingual/status'),
  });

  const tabs: { id: Tab; label: string }[] = useMemo(
    () => [
      { id: 'search', label: 'Cross-lingual поиск' },
      { id: 'detect', label: 'Детект языка / OCR' },
      { id: 'demo', label: 'Recall на «грязном» ru' },
    ],
    [],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Languages size={16} className="text-copper" /> ru↔en cross-lingual поиск
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          мультиязычные эмбеддинги · детект языка + OCR-устойчивость · §23.17
          {status.data && (
            <>
              {' · '}
              {status.data.embedding_model}
              {' · узлов: '}
              {status.data.nodes_indexed}
              {status.data.nodes_by_language &&
                ` (${Object.entries(status.data.nodes_by_language)
                  .map(([k, v]) => `${k}:${v}`)
                  .join(' ')})`}
            </>
          )}
        </div>

        <div className="mt-3 flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={
                'rounded-md px-3 py-1.5 text-xs transition ' +
                (tab === t.id
                  ? 'bg-copper/15 text-copper'
                  : 'text-muted hover:bg-surface/60 hover:text-nickel')
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {tab === 'search' && <SearchTab />}
        {tab === 'detect' && <DetectTab />}
        {tab === 'demo' && <DemoTab />}
      </div>
    </div>
  );
}
