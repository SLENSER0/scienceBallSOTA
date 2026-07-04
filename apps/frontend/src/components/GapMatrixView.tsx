import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Grid3x3, Loader2, TriangleAlert, X } from 'lucide-react';
import { api } from '../api';

// Gap-матрица: heatmap gap-type × domain (§17.14 / §5.2.7).
//
// Бэкенд `GET /gaps/matrix` уже отдаёт готовую матрицу счётчиков пробелов
// (`{ matrix: { gap_type: { domain: count } } }`) — здесь она превращается в
// цветовую карту: чем ярче ячейка, тем больше пробелов в этой паре
// «тип × домен». Клик по ячейке — drill-down в конкретный список пробелов
// (`GET /gaps?gap_type=&domain=`), который бэкенд тоже уже умеет фильтровать.
//
// Реализовано без внешних chart-зависимостей (чистый SVG/CSS-grid), чтобы карта
// оставалась лёгкой, темизируемой и всегда собираемой. Опциональный апгрейд на
// ECharts `heatmap` series описан в wiring.

type GapMatrix = Record<string, Record<string, number>>;

const DOMAIN_RU: Record<string, string> = {
  hydrometallurgy: 'Гидромет',
  pyrometallurgy: 'Пиромет',
  electrometallurgy: 'Электромет',
  mineral_processing: 'Обогащение',
  waste_processing: 'Отходы',
  water_treatment: 'Водоочистка',
  environment: 'Экология',
  '?': 'н/д',
};

// Все 9 типов пробелов §11.1 + человекочитаемые подписи.
const GAP_TYPE_RU: Record<string, string> = {
  missing_property_value: 'Нет значения свойства',
  missing_baseline: 'Нет базлайна',
  missing_processing_parameter: 'Нет параметра обработки',
  missing_equipment: 'Нет оборудования',
  missing_unit: 'Нет единицы',
  unverified_claim: 'Непроверенное утверждение',
  contradictory_measurements: 'Противоречивые измерения',
  low_coverage_material: 'Низкое покрытие материала',
  orphan_entity: 'Сирота-сущность',
  '?': 'Без типа',
};

const ruDomain = (d: string) => DOMAIN_RU[d] ?? d;
const ruType = (t: string) => GAP_TYPE_RU[t] ?? t;

// Медно-охровая последовательная шкала (0 → фон, max → яркая медь).
function cellStyle(count: number, max: number): React.CSSProperties {
  if (count <= 0) return { background: 'transparent' };
  // gamma < 1 подсвечивает мелкие значения, чтобы «редкие» пробелы были видны
  const t = max <= 0 ? 0 : Math.pow(count / max, 0.6);
  const alpha = 0.1 + t * 0.85;
  return {
    background: `rgba(184, 115, 51, ${alpha.toFixed(3)})`,
    color: t > 0.55 ? '#141414' : undefined,
  };
}

export function GapMatrixView() {
  const q = useQuery({
    queryKey: ['gaps-matrix'],
    queryFn: () => api.gapsMatrix(),
    staleTime: 5 * 60_000,
  });

  const [cell, setCell] = useState<{ type: string; domain: string } | null>(null);

  const { rows, cols, max, total } = useMemo(() => {
    const matrix: GapMatrix = q.data?.matrix ?? {};
    const rowKeys = Object.keys(matrix);
    const colSet = new Set<string>();
    let mx = 0;
    let tot = 0;
    for (const r of rowKeys) {
      for (const [c, v] of Object.entries(matrix[r])) {
        colSet.add(c);
        if (v > mx) mx = v;
        tot += v;
      }
    }
    // Стабильный порядок: типы по канону §11.1, домены по DOMAIN_RU.
    const typeOrder = Object.keys(GAP_TYPE_RU);
    const domOrder = Object.keys(DOMAIN_RU);
    const rk = rowKeys.sort(
      (a, b) => (typeOrder.indexOf(a) + 1 || 99) - (typeOrder.indexOf(b) + 1 || 99),
    );
    const ck = [...colSet].sort(
      (a, b) => (domOrder.indexOf(a) + 1 || 99) - (domOrder.indexOf(b) + 1 || 99),
    );
    return { rows: rk, cols: ck, max: mx, total: tot };
  }, [q.data]);

  const get = (t: string, d: string): number => q.data?.matrix?.[t]?.[d] ?? 0;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">gap-матрица · тепловая карта</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Grid3x3 size={22} className="text-copper" /> Карта пробелов: тип × домен
        </h1>
        <p className="mt-1 text-sm text-faint">
          Плотность пробелов знаний по паре «тип × домен». Ярче ячейка — больше
          недостающих данных. Клик по ячейке раскрывает конкретный список пробелов.
        </p>

        {q.isLoading ? (
          <div className="mt-10 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> загрузка матрицы…
          </div>
        ) : q.isError ? (
          <div
            className="panel mt-8 flex items-center justify-center gap-2 py-8 text-center font-mono text-[12px]"
            style={{ color: '#E5484D' }}
          >
            <TriangleAlert size={15} /> не удалось загрузить /gaps/matrix
          </div>
        ) : rows.length === 0 || cols.length === 0 ? (
          <div className="panel mt-8 py-12 text-center font-mono text-[11px] text-faint">
            пробелов не найдено — матрица пуста
          </div>
        ) : (
          <>
            <div className="mt-5 overflow-x-auto">
              <div
                className="grid gap-1"
                style={{
                  gridTemplateColumns: `minmax(190px, max-content) repeat(${cols.length}, minmax(72px, 1fr))`,
                }}
              >
                {/* Верхняя строка: домены */}
                <div />
                {cols.map((c) => (
                  <div
                    key={c}
                    className="pb-1 text-center font-mono text-[10px] uppercase tracking-wide text-faint"
                    title={c}
                  >
                    {ruDomain(c)}
                  </div>
                ))}

                {/* Строки: тип пробела + ячейки */}
                {rows.map((t) => (
                  <FragmentRow
                    key={t}
                    t={t}
                    cols={cols}
                    get={get}
                    max={max}
                    onPick={(d) => setCell({ type: t, domain: d })}
                  />
                ))}
              </div>
            </div>

            {/* Легенда */}
            <div className="mt-4 flex items-center gap-3 font-mono text-[10px] text-faint">
              <span>0</span>
              <div
                className="h-2 w-40 rounded-full"
                style={{
                  background:
                    'linear-gradient(90deg, rgba(184,115,51,0.10), rgba(184,115,51,0.95))',
                }}
              />
              <span>{max}</span>
              <span className="ml-3">всего пробелов: {total}</span>
            </div>
          </>
        )}

        {cell && (
          <CellDrill
            type={cell.type}
            domain={cell.domain}
            count={get(cell.type, cell.domain)}
            onClose={() => setCell(null)}
          />
        )}
      </div>
    </div>
  );
}

function FragmentRow({
  t,
  cols,
  get,
  max,
  onPick,
}: {
  t: string;
  cols: string[];
  get: (t: string, d: string) => number;
  max: number;
  onPick: (d: string) => void;
}) {
  return (
    <>
      <div
        className="flex items-center pr-2 text-right text-[12px] text-muted"
        title={t}
      >
        <span className="ml-auto truncate">{ruType(t)}</span>
      </div>
      {cols.map((d) => {
        const v = get(t, d);
        return (
          <button
            key={d}
            type="button"
            disabled={v <= 0}
            onClick={() => onPick(d)}
            style={cellStyle(v, max)}
            title={`${ruType(t)} × ${ruDomain(d)}: ${v}`}
            className={`flex h-11 items-center justify-center rounded border border-line/60 font-mono text-[12px] transition-colors ${
              v > 0 ? 'cursor-pointer hover:border-copper' : 'cursor-default text-faint/40'
            }`}
          >
            {v > 0 ? v : ''}
          </button>
        );
      })}
    </>
  );
}

// Drill-down: список конкретных пробелов для выбранной пары «тип × домен».
function CellDrill({
  type,
  domain,
  count,
  onClose,
}: {
  type: string;
  domain: string;
  count: number;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ['gaps-cell', type, domain],
    queryFn: () => api.gapsList({ gapType: type, domain, limit: 100 }),
    enabled: count > 0,
    staleTime: 60_000,
  });
  const gaps = q.data?.gaps ?? [];

  return (
    <div className="panel mt-5 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="eyebrow">drill-down</div>
          <div className="text-sm font-medium text-ink">
            {ruType(type)} <span className="text-faint">×</span> {ruDomain(domain)}
          </div>
          <div className="font-mono text-[10px] text-faint">{count} пробел(ов)</div>
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
          <Loader2 size={13} className="animate-spin text-copper" /> загрузка пробелов…
        </div>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {gaps.map((g) => (
            <li
              key={g.id}
              className="flex items-center gap-2 rounded border border-line/60 px-2.5 py-1.5 text-[13px] text-muted"
            >
              <span className="font-mono text-[9px] text-faint">{g.id}</span>
              <span className="truncate text-ink">{g.name}</span>
            </li>
          ))}
          {gaps.length === 0 && (
            <li className="font-mono text-[11px] text-faint">пусто</li>
          )}
        </ul>
      )}
    </div>
  );
}
