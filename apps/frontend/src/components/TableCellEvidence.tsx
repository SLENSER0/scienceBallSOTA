import { useQuery } from '@tanstack/react-query';
import { Loader2, Table2 } from 'lucide-react';
import { api } from '../api';

// Table-cell Evidence (§6.10/§8.3): клик по числу → подсветка ТОЧНОЙ ячейки
// исходной таблицы. Число, извлечённое из таблицы, несёт локатор table_id + row +
// col; этот компонент восстанавливает сетку и обводит ровно ту ячейку, из которой
// пришло значение — «максимальный уровень доверия»: значение видно подсвеченным в
// реальной таблице документа, а не просто ссылкой на страницу.

export interface TableCellEvidencePayload {
  evidenceId: string | null;
  isTableCell: boolean;
  docId: string | null;
  page: number | null;
  tableId: string | null;
  rowIndex: number | null;
  colIndex: number | null;
  locatorValid: boolean;
  grid: string[][];
  nRows: number;
  nCols: number;
  highlight: { row: number; col: number };
  cellText: string;
  source: string; // parsed | reconstructed | cell-only | none
  detail: string;
}

const SOURCE_LABEL: Record<string, string> = {
  parsed: 'распарсенная таблица',
  reconstructed: 'восстановлено из evidence',
  'cell-only': 'только ячейка',
  none: '—',
};

export function TableCellEvidence({ evidenceId }: { evidenceId: string }) {
  const q = useQuery({
    queryKey: ['table-cell-evidence', evidenceId],
    queryFn: () => api.evidenceTableCell(evidenceId),
    enabled: !!evidenceId,
  });

  if (q.isLoading) {
    return (
      <div className="flex items-center gap-2 font-mono text-xs text-faint">
        <Loader2 size={14} className="animate-spin text-copper" /> трассировка ячейки…
      </div>
    );
  }
  if (!q.data) {
    return <div className="text-sm text-faint">Ячейка недоступна.</div>;
  }
  const d = q.data;

  if (!d.isTableCell) {
    return (
      <div className="rounded border border-line bg-surface/60 px-3 py-2 text-sm text-faint">
        Это доказательство не является ячейкой таблицы — трассировка к ячейке недоступна.
      </div>
    );
  }

  return (
    <div className="animate-rise space-y-3">
      <div className="flex items-center gap-2">
        <Table2 size={15} className="text-copper" />
        <span className="eyebrow">исходная таблица</span>
        <span className="ml-auto rounded-full border border-line bg-surface/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-faint">
          {SOURCE_LABEL[d.source] ?? d.source}
        </span>
      </div>

      <TraceRow k="документ" v={d.docId ?? '—'} />
      <div className="grid grid-cols-3 gap-2">
        <Chip k="table_id" v={d.tableId ?? '—'} />
        <Chip k="row" v={d.rowIndex ?? '—'} />
        <Chip k="col" v={d.colIndex ?? '—'} />
      </div>

      <div className="overflow-x-auto rounded border border-line bg-graphite/60">
        <table className="w-full border-collapse font-mono text-[11px]">
          <tbody>
            {d.grid.map((row, r) => (
              <tr key={r}>
                {row.map((cell, c) => {
                  const hit = r === d.highlight.row && c === d.highlight.col;
                  const header = r === 0;
                  return (
                    <td
                      key={c}
                      className={[
                        'border border-line/60 px-2 py-1 align-top',
                        hit
                          ? 'bg-copper/25 font-semibold text-ink ring-2 ring-inset ring-copper'
                          : header
                            ? 'bg-surface/70 text-nickel'
                            : 'text-ink/85',
                      ].join(' ')}
                      title={hit ? `row ${r}, col ${c}` : undefined}
                    >
                      {cell || '·'}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded border-l-2 border-copper bg-surface/60 px-3 py-2">
        <div className="eyebrow mb-1">извлечённое значение</div>
        <div className="font-mono text-sm text-ink">{d.cellText || '—'}</div>
      </div>

      <div className="font-mono text-[10px] leading-relaxed text-faint">
        {d.detail}
        {!d.locatorValid && (
          <span className="ml-1 text-amber-400">· локатор неполный (§8.3)</span>
        )}
      </div>
    </div>
  );
}

function TraceRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/50 pb-1.5">
      <span className="font-mono text-[11px] uppercase tracking-wide text-faint">{k}</span>
      <span className="truncate text-right font-mono text-xs text-ink/90" title={v}>
        {v}
      </span>
    </div>
  );
}

function Chip({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="rounded border border-line bg-surface/60 px-2 py-1.5 text-center">
      <div className="font-mono text-[10px] uppercase tracking-wide text-faint">{k}</div>
      <div className="truncate font-mono text-xs text-ink/90" title={String(v)}>
        {v}
      </div>
    </div>
  );
}
