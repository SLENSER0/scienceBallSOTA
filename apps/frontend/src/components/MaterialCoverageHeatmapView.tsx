import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Grid3x3, Loader2, TriangleAlert, X, CheckCircle2, CircleDashed } from 'lucide-react';

// Тепловая карта покрытия «материал × свойство» (§17.14 / §5.2.7 Gap Dashboard).
//
// Бэкенд `GET /api/v1/coverage/matrix` уже отдаёт готовую матрицу покрытия
// (переиспользует `kg_retrievers.coverage_matrix.build_coverage_matrix`): для каждой
// пары «материал × свойство» — статус covered/absent, число измерений-доказательств
// (`evidence_count`) и подтверждённых (`verified_count`). Здесь это превращается в
// цветовую карту: чем ярче ячейка, тем больше измерений; пустые ячейки (absent) —
// это и есть пробелы знаний, они подсвечены пунктирной «полой» рамкой (§17 SOTA #4).
// Клик по ячейке → drill-down (`GET /api/v1/coverage/cell`) с конкретными
// измерениями и пробелами для пары.
//
// Рендер — на чистом SVG/CSS-grid (совместимо с текущей сборкой, без внешних
// chart-зависимостей). Точечный апгрейд на ECharts `heatmap` series описан в wiring.

type Cell = {
  material_id: string;
  material_name: string;
  property: string;
  status: 'covered' | 'absent';
  evidence_count: number;
  verified_count: number;
  gap: boolean;
};

type MatrixResp = {
  materials: { id: string; name: string }[];
  properties: string[];
  cells: Cell[];
  max_evidence: number;
  summary: { covered: number; absent: number; total: number; coverage_ratio: number };
};

type CellResp = {
  material_id: string;
  property: string;
  measurements: { id: string; name: string; verified: boolean; confidence: number | null }[];
  gaps: { id: string; name: string; gap_type: string | null }[];
  counts: { measurements: number; gaps: number };
};

// Человекочитаемые подписи свойств (DEFAULT_PROPERTIES §25).
const PROPERTY_RU: Record<string, string> = {
  recovery: 'Извлечение',
  concentration: 'Концентрация',
  current_density: 'Плотность тока',
  flow_velocity: 'Скорость потока',
  removal_efficiency: 'Степень очистки',
  energy_consumption: 'Энергозатраты',
  capex: 'CapEx',
  opex: 'OpEx',
};
const ruProp = (p: string) => PROPERTY_RU[p] ?? p;

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

async function cmFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// Медно-охровая последовательная шкала по числу измерений (evidence_count).
// gamma < 1 подсвечивает малые значения — «редкие» измерения остаются видимыми.
function coveredStyle(count: number, max: number): React.CSSProperties {
  const t = max <= 0 ? 0 : Math.pow(count / max, 0.55);
  const alpha = 0.14 + t * 0.82;
  return {
    background: `rgba(184, 115, 51, ${alpha.toFixed(3)})`,
    color: t > 0.5 ? '#141414' : undefined,
  };
}

export function MaterialCoverageHeatmapView({ embedded = false }: { embedded?: boolean } = {}) {
  const q = useQuery({
    queryKey: ['coverage-heatmap'],
    queryFn: () => cmFetch<MatrixResp>('/api/v1/coverage/matrix?material_limit=60'),
    staleTime: 5 * 60_000,
  });

  const [sel, setSel] = useState<Cell | null>(null);

  const { byKey, materials, properties } = useMemo(() => {
    const cells = q.data?.cells ?? [];
    const map = new Map<string, Cell>();
    for (const c of cells) map.set(`${c.material_id}|${c.property}`, c);
    return {
      byKey: map,
      materials: q.data?.materials ?? [],
      properties: q.data?.properties ?? [],
    };
  }, [q.data]);

  const max = q.data?.max_evidence ?? 0;
  const summary = q.data?.summary;

  const header = embedded ? (
    <div className="mb-3 flex items-center gap-2 text-sm text-nickel">
      <Grid3x3 size={16} className="text-copper" /> Покрытие: материал × свойство
    </div>
  ) : (
    <>
      <div className="eyebrow mb-1">карта покрытия · тепловая карта</div>
      <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
        <Grid3x3 size={22} className="text-copper" /> Покрытие: материал × свойство
      </h1>
      <p className="mt-1 text-sm text-faint">
        Плотность измерений по паре «материал × свойство». Ярче ячейка — больше
        доказательств; пунктирная полая ячейка — пробел (свойство не измерено). Клик по
        ячейке раскрывает измерения и пробелы для пары.
      </p>
    </>
  );

  const inner = (
    <>
      {header}

        {q.isLoading ? (
          <div className="mt-10 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> загрузка матрицы покрытия…
          </div>
        ) : q.isError ? (
          <div
            className="panel mt-8 flex items-center justify-center gap-2 py-8 text-center font-mono text-[12px]"
            style={{ color: '#E5484D' }}
          >
            <TriangleAlert size={15} /> не удалось загрузить /coverage/matrix
          </div>
        ) : materials.length === 0 || properties.length === 0 ? (
          <div className="panel mt-8 py-12 text-center font-mono text-[11px] text-faint">
            матрица пуста — материалов или свойств не найдено
          </div>
        ) : (
          <>
            {summary && (
              <div className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11px]">
                <span className="chip border-verified/40 text-verified">
                  покрыто {summary.covered}
                </span>
                <span className="chip border-gap/40 text-gap">пробелов {summary.absent}</span>
                <span className="chip text-faint">
                  покрытие {(summary.coverage_ratio * 100).toFixed(1)}%
                </span>
              </div>
            )}

            <div className="mt-5 overflow-x-auto">
              <div
                className="grid gap-1"
                style={{
                  gridTemplateColumns: `minmax(150px, max-content) repeat(${properties.length}, minmax(76px, 1fr))`,
                }}
              >
                {/* Верхняя строка: свойства */}
                <div />
                {properties.map((p) => (
                  <div
                    key={p}
                    className="pb-1 text-center font-mono text-[10px] uppercase tracking-wide text-faint"
                    title={p}
                  >
                    {ruProp(p)}
                  </div>
                ))}

                {/* Строки: материал + ячейки */}
                {materials.map((m) => (
                  <MaterialRow
                    key={m.id}
                    material={m}
                    properties={properties}
                    byKey={byKey}
                    max={max}
                    onPick={setSel}
                  />
                ))}
              </div>
            </div>

            {/* Легенда */}
            <div className="mt-4 flex flex-wrap items-center gap-3 font-mono text-[10px] text-faint">
              <span>0</span>
              <div
                className="h-2 w-40 rounded-full"
                style={{
                  background:
                    'linear-gradient(90deg, rgba(184,115,51,0.14), rgba(184,115,51,0.96))',
                }}
              />
              <span>{max} измер.</span>
              <span className="ml-2 flex items-center gap-1">
                <CircleDashed size={12} className="text-gap" /> пробел
              </span>
            </div>
          </>
        )}

      {sel && <CellDrill cell={sel} onClose={() => setSel(null)} />}
    </>
  );

  if (embedded) return <section>{inner}</section>;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">{inner}</div>
    </div>
  );
}

function MaterialRow({
  material,
  properties,
  byKey,
  max,
  onPick,
}: {
  material: { id: string; name: string };
  properties: string[];
  byKey: Map<string, Cell>;
  max: number;
  onPick: (c: Cell) => void;
}) {
  return (
    <>
      <div className="flex items-center pr-2 text-right text-[12px] text-muted" title={material.id}>
        <span className="ml-auto truncate">{material.name}</span>
      </div>
      {properties.map((p) => {
        const c = byKey.get(`${material.id}|${p}`);
        const evidence = c?.evidence_count ?? 0;
        const isGap = !c || c.gap;
        return (
          <button
            key={p}
            type="button"
            onClick={() => c && onPick(c)}
            disabled={!c}
            title={
              c
                ? `${material.name} × ${ruProp(p)}: ${evidence} измер. (${c.verified_count} подтв.)`
                : ''
            }
            style={isGap ? undefined : coveredStyle(evidence, max)}
            className={`flex h-11 items-center justify-center rounded border font-mono text-[12px] transition-colors ${
              isGap
                ? 'cursor-pointer border-dashed border-gap/40 text-gap/60 hover:border-gap'
                : 'cursor-pointer border-line/60 hover:border-copper'
            }`}
          >
            {isGap ? '·' : evidence}
          </button>
        );
      })}
    </>
  );
}

// Drill-down: измерения и пробелы для выбранной пары «материал × свойство».
function CellDrill({ cell, onClose }: { cell: Cell; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['coverage-cell', cell.material_id, cell.property],
    queryFn: () =>
      cmFetch<CellResp>(
        `/api/v1/coverage/cell?material_id=${encodeURIComponent(cell.material_id)}&property=${encodeURIComponent(cell.property)}`,
      ),
    staleTime: 60_000,
  });
  const measurements = q.data?.measurements ?? [];
  const gaps = q.data?.gaps ?? [];

  return (
    <div className="panel mt-5 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="eyebrow">drill-down</div>
          <div className="text-sm font-medium text-ink">
            {cell.material_name} <span className="text-faint">×</span> {ruProp(cell.property)}
          </div>
          <div className="font-mono text-[10px] text-faint">
            {cell.gap ? 'пробел' : 'покрыто'} · {cell.evidence_count} измер. ·{' '}
            {cell.verified_count} подтв.
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-faint hover:text-nickel"
          aria-label="закрыть"
        >
          <X size={15} />
        </button>
      </div>

      {q.isLoading ? (
        <div className="mt-3 flex items-center gap-2 font-mono text-[11px] text-faint">
          <Loader2 size={13} className="animate-spin text-copper" /> загрузка…
        </div>
      ) : (
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
              <CheckCircle2 size={12} className="text-verified" /> измерения ({measurements.length})
            </div>
            <ul className="space-y-1.5">
              {measurements.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center gap-2 rounded border border-line/60 px-2.5 py-1.5 text-[12px] text-muted"
                >
                  <span className="truncate text-ink">{m.name}</span>
                  {m.verified && (
                    <span className="ml-auto chip border-verified/40 text-verified">подтв.</span>
                  )}
                  {m.confidence != null && (
                    <span className="font-mono text-[9px] text-faint">
                      {m.confidence.toFixed(2)}
                    </span>
                  )}
                </li>
              ))}
              {measurements.length === 0 && (
                <li className="font-mono text-[11px] text-faint">нет измерений</li>
              )}
            </ul>
          </div>
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-faint">
              <CircleDashed size={12} className="text-gap" /> пробелы ({gaps.length})
            </div>
            <ul className="space-y-1.5">
              {gaps.map((g) => (
                <li
                  key={g.id}
                  className="flex items-center gap-2 rounded border border-gap/30 px-2.5 py-1.5 text-[12px] text-muted"
                >
                  <span className="truncate text-ink">{g.name}</span>
                  {g.gap_type && (
                    <span className="ml-auto font-mono text-[9px] text-gap/80">{g.gap_type}</span>
                  )}
                </li>
              ))}
              {gaps.length === 0 && (
                <li className="font-mono text-[11px] text-faint">нет зафиксированных пробелов</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
