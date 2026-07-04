import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import type { CoverageDomain } from '../types';

const LABEL: Record<string, string> = {
  hydrometallurgy: 'Гидрометаллургия',
  pyrometallurgy: 'Пирометаллургия',
  environment: 'Экология',
  water_treatment: 'Водоподготовка',
  waste_processing: 'Переработка отходов',
  mineral_processing: 'Обогащение',
  electrometallurgy: 'Электрометаллургия',
};

export function CoverageView({ embedded = false }: { embedded?: boolean } = {}) {
  const { data, isLoading } = useQuery({ queryKey: ['coverage'], queryFn: api.coverage });

  const grid = (
    <>
      {isLoading && <div className="font-mono text-sm text-faint">загрузка…</div>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.domains
          .slice()
          .sort((a, b) => b.sources + b.measurements - (a.sources + a.measurements))
          .map((d) => (
            <DomainCard key={d.domain} d={d} />
          ))}
      </div>
    </>
  );

  if (embedded) {
    return (
      <section>
        <div className="mb-3 text-sm text-nickel">Покрытие знаний по направлениям</div>
        {grid}
      </section>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">дашборд руководителя</div>
        <h2 className="mb-5 font-display text-2xl font-semibold">Покрытие знаний по направлениям</h2>
        {grid}
      </div>
    </div>
  );
}

function DomainCard({ d }: { d: CoverageDomain }) {
  const risk = d.risk === 'high';
  return (
    <div className={`panel p-4 ${risk ? 'border-gap/40' : ''}`}>
      <div className="mb-3 flex items-start justify-between">
        <h3 className="font-display text-base text-ink">{LABEL[d.domain] ?? d.domain}</h3>
        <span
          className={`chip ${risk ? 'border-gap/40 text-gap' : 'border-verified/40 text-verified'}`}
        >
          {risk ? 'зона риска' : 'покрыто'}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Stat n={d.sources} label="источн." />
        <Stat n={d.technologies} label="решений" />
        <Stat n={d.measurements} label="измер." />
        <Stat n={d.gaps} label="пробелов" tone={d.gaps ? 'gap' : undefined} />
        <Stat n={d.contradictions} label="противор." tone={d.contradictions ? 'contradiction' : undefined} />
        <Stat n={d.sources + d.technologies} label="всего" />
      </div>
    </div>
  );
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: 'gap' | 'contradiction' }) {
  const color = tone === 'gap' ? 'text-gap' : tone === 'contradiction' ? 'text-contradiction' : 'text-nickel-bright';
  return (
    <div className="rounded bg-void/40 py-2">
      <div className={`metric text-xl ${color}`}>{n}</div>
      <div className="font-mono text-[10px] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
