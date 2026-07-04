import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, Loader2, Highlighter, FileText, Tag } from 'lucide-react';
import { api } from '../api';
import type { HighlightSearchResponse, HighlightHit } from '../types';

// §4.7 — Подсветка совпадений (<em>-фрагменты) в результатах поиска.
// Бэкенд GET /api/v1/search/highlight ищет узлы по запросу и для каждого хита
// возвращает фрагменты того поля, где нашлось совпадение, с термами запроса,
// обёрнутыми в <em>. Здесь фрагменты рендерятся с подсветкой спана — точный
// кусок текста, по которому найден результат (evidence/доверие).

const FIELD_RU: Record<string, string> = {
  text: 'текст',
  name: 'название',
  aliases_text: 'синонимы',
  canonical_name: 'канон. имя',
};

// Бэкенд экранирует весь исходный текст (html.escape) и вставляет ТОЛЬКО теги
// <em>/</em>, поэтому в html не может оказаться чужой разметки — безопасно
// отрисовать напрямую и подсветить спан через CSS.
function Fragment({ html }: { html: string }) {
  return (
    <span
      className="[&>em]:rounded-sm [&>em]:bg-copper/25 [&>em]:px-0.5 [&>em]:not-italic [&>em]:font-medium [&>em]:text-copper"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function HitCard({ h }: { h: HighlightHit }) {
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-nickel">{h.name ?? h.id}</span>
        {h.type && <span className="chip text-faint border-line text-[9px]">{h.type}</span>}
        <span className="ml-auto flex items-center gap-1 font-mono text-[10px] text-faint">
          <Highlighter size={11} className="text-copper" />
          {Math.round(h.score * 100)}%
        </span>
      </div>

      <div className="mt-2 space-y-1.5">
        {h.fragments.map((f, i) => (
          <div key={i} className="rounded bg-surface/50 px-2.5 py-1.5 text-xs leading-relaxed text-muted">
            <Fragment html={f.html} />
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10px] text-faint">
        <span className="inline-flex items-center gap-1">
          <Tag size={10} /> поле: {FIELD_RU[h.field] ?? h.field}
        </span>
        {h.doc_id && (
          <span className="inline-flex items-center gap-1">
            <FileText size={10} /> {h.doc_id}
            {h.page != null && ` · с. ${h.page}`}
          </span>
        )}
        {h.review_status && h.review_status !== 'pending' && (
          <span className="chip text-verified border-verified/40 text-[9px]">{h.review_status}</span>
        )}
        <span className="ml-auto">{h.id}</span>
      </div>
    </div>
  );
}

export function SearchHighlightView() {
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');

  const q = useQuery<HighlightSearchResponse>({
    queryKey: ['search-highlight', query],
    queryFn: () => api.searchHighlight(query),
    enabled: query.trim().length > 0,
  });

  const results = q.data?.results ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Highlighter size={16} className="text-copper" /> Подсветка совпадений в поиске
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          &lt;em&gt;-фрагменты · точный спан хита · §4.7
        </div>

        <form
          className="mt-3 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(input.trim());
          }}
        >
          <div className="relative flex-1">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="напр. старение твёрдость Al-Cu…"
              className="w-full rounded-md border border-line bg-surface/60 py-2 pl-8 pr-3 text-sm text-nickel placeholder:text-faint focus:border-copper/50 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={!input.trim()}
            className="inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-2 text-xs text-copper transition hover:bg-copper/20 disabled:opacity-40"
          >
            <Search size={13} /> Найти
          </button>
        </form>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {!query.trim() ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <Highlighter size={30} className="mx-auto mb-2 text-faint" />
              <div className="font-mono text-xs text-faint">
                введите запрос — совпадения будут подсвечены во фрагментах
              </div>
            </div>
          </div>
        ) : q.isLoading ? (
          <div className="flex items-center gap-2 font-mono text-xs text-faint">
            <Loader2 size={14} className="animate-spin text-copper" /> поиск…
          </div>
        ) : q.isError ? (
          <div className="text-sm text-contradiction">Не удалось выполнить поиск.</div>
        ) : results.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <Search size={30} className="mx-auto mb-2 text-faint" />
              <div className="font-mono text-xs text-faint">ничего не найдено по «{query}»</div>
            </div>
          </div>
        ) : (
          <div className="mx-auto grid max-w-3xl gap-3">
            <div className="font-mono text-[10px] text-faint">
              {q.data?.count ?? 0} хитов · термы подсвечены
            </div>
            {results.map((h) => (
              <HitCard key={h.id} h={h} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
