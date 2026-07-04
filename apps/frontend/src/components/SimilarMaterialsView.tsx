import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Atom, FlaskConical, Gauge, Microscope, Sparkles, TriangleAlert, Wrench } from 'lucide-react';
import { api } from '../api';

// §13.11 «Похожие материалы» — node similarity (Mode D) как объяснимая фича.
// «Найди материалы, похожие на X по режимам обработки и свойствам». Метрика —
// Jaccard атрибутных соседств (как gds.nodeSimilarity), но мы показываем САМИ
// общие узлы, сгруппированные по фасетам: почему два материала похожи.

const FACET_META: Record<
  string,
  { label: string; Icon: typeof Gauge; tint: string }
> = {
  ProcessingRegime: { label: 'Режимы', Icon: Gauge, tint: 'text-copper' },
  Property: { label: 'Свойства', Icon: Atom, tint: 'text-nickel-bright' },
  Method: { label: 'Методы', Icon: Microscope, tint: 'text-copper' },
  Equipment: { label: 'Оборудование', Icon: Wrench, tint: 'text-nickel-bright' },
};
const FACET_ORDER = ['ProcessingRegime', 'Property', 'Method', 'Equipment'];

export function SimilarMaterialsView() {
  const [seed, setSeed] = useState('');
  const [active, setActive] = useState<Record<string, boolean>>({
    ProcessingRegime: true,
    Property: true,
    Method: true,
    Equipment: true,
  });

  const seeds = useQuery({
    queryKey: ['sm-seeds'],
    queryFn: () => api.similarMaterialsSeeds(),
  });
  const seedId = seed || seeds.data?.seeds[0]?.id || '';

  const facetsParam = useMemo(
    () => FACET_ORDER.filter((f) => active[f]).join(','),
    [active],
  );

  const sim = useQuery({
    queryKey: ['sm-similar', seedId, facetsParam],
    queryFn: () => api.similarMaterials(seedId, 12, facetsParam),
    enabled: !!seedId && facetsParam.length > 0,
  });

  const toggle = (f: string) =>
    setActive((prev) => ({ ...prev, [f]: !prev[f] }));

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">node similarity · Mode D · §13.11</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Похожие материалы</h2>
        <p className="mb-5 max-w-2xl text-sm text-faint">
          Сходство материалов по режимам обработки и свойствам — мера Jaccard общих атрибутов
          (как <span className="font-mono">gds.nodeSimilarity</span>). В отличие от «сырого»
          nodeSimilarity, показываем сами общие узлы: <em>почему</em> два материала похожи.
        </p>

        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Материал</span>
            <select
              value={seedId}
              onChange={(e) => setSeed(e.target.value)}
              className="min-w-72 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
            >
              {seeds.data?.seeds.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.attributes} атр.
                </option>
              ))}
            </select>
          </label>

          <div className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-faint">Сравнивать по</span>
            <div className="flex flex-wrap gap-1.5">
              {FACET_ORDER.map((f) => {
                const meta = FACET_META[f];
                const on = active[f];
                return (
                  <button
                    key={f}
                    type="button"
                    onClick={() => toggle(f)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition ${
                      on
                        ? 'border-copper/50 bg-copper/10 text-ink'
                        : 'border-line bg-surface/40 text-faint hover:border-copper/30'
                    }`}
                  >
                    <meta.Icon size={12} className={on ? meta.tint : 'text-faint'} />
                    {meta.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {sim.data && sim.data.seed_attributes.length > 0 && (
          <div className="mb-4 rounded-lg border border-line bg-surface/40 px-4 py-3">
            <div className="mb-1.5 text-[11px] uppercase tracking-wide text-faint">
              Профиль «{sim.data.seed.name}»
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sim.data.seed_attributes.slice(0, 24).map((a) => {
                const meta = FACET_META[a.label] ?? FACET_META.Property;
                return (
                  <span
                    key={a.id}
                    className="inline-flex items-center gap-1 rounded border border-line/70 bg-surface/50 px-1.5 py-0.5 text-[10px] text-faint"
                  >
                    <meta.Icon size={10} className={meta.tint} />
                    {a.name}
                  </span>
                );
              })}
              {sim.data.seed_attributes.length > 24 && (
                <span className="text-[10px] text-faint/80">
                  +{sim.data.seed_attributes.length - 24}
                </span>
              )}
            </div>
          </div>
        )}

        {facetsParam.length === 0 && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            Выберите хотя бы один фасет для сравнения.
          </div>
        )}

        {sim.isLoading && (
          <div className="text-sm text-faint">Считаем сходство по общим атрибутам…</div>
        )}
        {sim.isError && (
          <div className="flex items-center gap-2 text-sm text-copper">
            <TriangleAlert size={15} /> Не удалось посчитать похожие материалы.
          </div>
        )}

        {sim.data && sim.data.count === 0 && facetsParam.length > 0 && (
          <div className="rounded-lg border border-line bg-surface/40 px-4 py-6 text-center text-sm text-faint">
            {sim.data.note ??
              'Нет материалов, разделяющих выбранные режимы/свойства с этим материалом.'}
          </div>
        )}

        {sim.data && sim.data.count > 0 && (
          <ul className="space-y-2.5">
            {sim.data.similar.map((m) => (
              <li
                key={m.id}
                className="rounded-lg border border-line bg-surface/50 px-4 py-3 transition hover:border-copper/40"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <FlaskConical size={15} className="shrink-0 text-copper" />
                    <span className="truncate font-medium text-ink">{m.name}</span>
                    <span className="shrink-0 font-mono text-[10px] text-faint">
                      {m.shared_count} общих
                    </span>
                  </div>
                  <span className="metric shrink-0 text-sm text-nickel-bright">
                    {Math.round(m.similarity * 100)}%
                  </span>
                </div>

                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-line/60">
                  <div
                    className="h-full rounded-full bg-copper/70"
                    style={{ width: `${Math.max(4, Math.round(m.similarity * 100))}%` }}
                  />
                </div>

                <div className="mt-2.5 space-y-1.5">
                  {FACET_ORDER.filter((f) => m.shared_by_facet[f]?.length).map((f) => {
                    const meta = FACET_META[f];
                    return (
                      <div key={f} className="flex items-start gap-1.5">
                        <meta.Icon size={12} className={`mt-0.5 shrink-0 ${meta.tint}`} />
                        <div className="flex flex-wrap gap-1">
                          {m.shared_by_facet[f].map((a) => (
                            <span
                              key={a.id}
                              className="rounded border border-line/70 bg-surface/40 px-1.5 py-0.5 text-[10px] text-faint"
                            >
                              {a.name}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
        )}

        {sim.data && sim.data.count > 0 && (
          <div className="mt-4 flex items-center gap-1.5 text-[11px] text-faint">
            <Sparkles size={12} className="text-copper" /> {sim.data.count} материалов, похожих на «
            {sim.data.seed.name}» · Jaccard общих {sim.data.facets.length} фасет(ов)
          </div>
        )}
      </div>
    </div>
  );
}
