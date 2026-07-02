import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { api } from '../api';

export function GlossaryView() {
  const [q, setQ] = useState('');
  const { data } = useQuery({ queryKey: ['glossary', q], queryFn: () => api.glossary(q) });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">RU / EN · единый словарь терминов</div>
        <h2 className="mb-4 font-display text-2xl font-semibold">Глоссарий предметной области</h2>
        <div className="panel mb-5 flex items-center gap-2 px-3 py-2">
          <Search size={16} className="text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="ПВП, catholyte, обессоливание, SO₂…"
            className="flex-1 bg-transparent py-1 text-sm text-ink placeholder:text-faint focus:outline-none"
          />
          <span className="metric text-xs text-faint">{data?.count ?? 0}</span>
        </div>
        <div className="grid gap-2">
          {data?.terms.map((t) => (
            <div key={t.id} className="panel flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
              <span className="font-medium text-ink">{t.canonical_ru}</span>
              <span className="text-faint">·</span>
              <span className="text-nickel">{t.canonical_en}</span>
              <span className="chip ml-auto text-faint">{t.type}</span>
              {t.domain && <span className="chip text-copper/80">{t.domain}</span>}
              <div className="w-full font-mono text-[11px] text-faint">
                {t.aliases.slice(0, 8).join(' · ')}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
