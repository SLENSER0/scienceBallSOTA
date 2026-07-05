import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, CircleCheck, CircleSlash, Download, FileText, Loader2, X } from 'lucide-react';
import { api } from '../api';
import { CallHistory } from './CallHistory';
import { DocumentViewer } from './DocumentUpload';
import { pushCall } from '../lib/callHistory';

type Cell = { value?: number; unit?: string; gap?: boolean; evidence_ids?: string[] };
// Applicability cell — prose + the corpus-text source it is grounded in (§17.19).
type ApplCell = { text: string; doc_id?: string | null; page?: number | null; evidence_ids?: string[] };

function isApplCell(v: unknown): v is ApplCell {
  return typeof v === 'object' && v !== null && 'text' in (v as object);
}

// Visible domestic-vs-foreign split (jury ask): map raw practice_type enum → отеч./заруб.
const PRACTICE_LABELS: Record<string, { short: string; domestic: boolean }> = {
  russia: { short: 'отеч.', domestic: true },
  cis: { short: 'отеч. (СНГ)', domestic: true },
  foreign: { short: 'заруб.', domestic: false },
  global: { short: 'заруб. (глоб.)', domestic: false },
};

// Flatten a comparison cell to plain text for CSV (§17.16).
function cellText(v: unknown): string {
  if (isApplCell(v)) return v.text ?? '';
  if (v && typeof v === 'object') {
    const c = v as Cell;
    if (c.gap) return '—';
    if (c.value !== undefined) return `${c.value}${c.unit ? ' ' + c.unit : ''}`;
    return '';
  }
  return v == null ? '' : String(v);
}

function downloadCsv(columns: string[], rows: Record<string, unknown>[]): void {
  const esc = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const lines = [columns.map(esc).join(',')];
  for (const row of rows) lines.push(columns.map((c) => esc(cellText(row[c]))).join(','));
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `klubok-compare-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const EXAMPLES = [
  'методы обессоливания воды: обратный осмос, ионный обмен, электродиализ',
  'методы удаления SO2 из отходящих газов',
];

export function CompareView() {
  const [q, setQ] = useState('');
  const [viewerDoc, setViewerDoc] = useState<string | null>(null);
  const cmp = useMutation({ mutationFn: (query: string) => api.comparison(query) });
  const runCompare = (query: string) => {
    const t = query.trim();
    if (!t) return;
    pushCall('compare', t);
    cmp.mutate(t);
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">сравнительный анализ технологий</div>
        <h2 className="mb-4 font-display text-2xl font-semibold">Таблица сравнения</h2>

        <div className="panel mb-4 flex items-end gap-2 p-1.5">
          <textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            rows={2}
            placeholder="Технологии для сравнения (материал / процесс / условия)…"
            className="min-h-[48px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-ink placeholder:text-faint focus:outline-none"
          />
          <button
            onClick={() => runCompare(q)}
            disabled={cmp.isPending || !q.trim()}
            className="btn-copper mb-1 mr-1 flex items-center gap-1.5"
          >
            {cmp.isPending ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
            Сравнить
          </button>
        </div>

        {!cmp.data && !cmp.isPending && (
          <div className="flex flex-col gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setQ(ex);
                  runCompare(ex);
                }}
                className="rounded-md border border-line bg-surface/40 px-3 py-2 text-left text-sm text-muted hover:border-copper/40 hover:text-ink"
              >
                {ex}
              </button>
            ))}
            <CallHistory
              feature="compare"
              onPick={(e) => {
                setQ(e.label);
                runCompare(e.label);
              }}
            />
          </div>
        )}

        {cmp.data && (
          <>
            <div className="mb-2 flex items-center gap-2">
              <span className="eyebrow">
                покрытие: {cmp.data.coverage.cells_with_evidence}/{cmp.data.coverage.cells_total}{' '}
                ячеек с доказательствами · {cmp.data.coverage.solutions} решений
              </span>
              <button
                onClick={() => downloadCsv(cmp.data!.columns, cmp.data!.rows)}
                className="chip ml-auto text-faint hover:border-copper/40 hover:text-copper"
                title="Экспорт таблицы в CSV"
              >
                <Download size={11} /> CSV
              </button>
            </div>
            <div className="panel overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    {cmp.data.columns.map((c) => (
                      <th
                        key={c}
                        className="whitespace-nowrap px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wide text-faint"
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cmp.data.rows.map((row, i) => (
                    <tr key={i} className="border-t border-line/60">
                      {cmp.data!.columns.map((c) => (
                        <td key={c} className="px-3 py-2 align-top">
                          <CellValue value={row[c]} onOpenSource={setViewerDoc} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
      {/* In-app corpus-text viewer for an applicability «источник» (reuses DocumentUpload's viewer). */}
      {viewerDoc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/70 p-4"
          onClick={() => setViewerDoc(null)}
        >
          <div className="panel w-full max-w-3xl p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-nickel">
                <FileText size={15} className="text-copper" /> Разбор документа
              </div>
              <button
                onClick={() => setViewerDoc(null)}
                className="rounded p-1 text-faint hover:text-copper"
                title="Закрыть"
              >
                <X size={16} />
              </button>
            </div>
            <DocumentViewer docId={viewerDoc} />
          </div>
        </div>
      )}
    </div>
  );
}

function CellValue({ value, onOpenSource }: { value: unknown; onOpenSource?: (docId: string) => void }) {
  // Applicability cell — prose + a link to the corpus text it is grounded in (§17.19).
  if (isApplCell(value)) {
    return (
      <span className="flex flex-col items-start gap-0.5">
        <span className="text-ink/90">{value.text}</span>
        {value.doc_id && (
          <button
            onClick={() => onOpenSource?.(value.doc_id!)}
            className="chip border-copper/40 text-copper hover:bg-copper/10"
            title={`Открыть источник в корпусе${value.page ? ` · стр. ${value.page}` : ''}`}
          >
            <FileText size={11} /> источник{value.page ? ` · стр. ${value.page}` : ''}
          </button>
        )}
      </span>
    );
  }
  if (typeof value === 'string') {
    const pr = PRACTICE_LABELS[value.toLowerCase()];
    if (pr)
      return (
        <span
          className={`chip ${pr.domestic ? 'border-verified/40 text-verified' : 'border-copper/40 text-copper'}`}
          title={`Практика: ${value}`}
        >
          {pr.short}
        </span>
      );
    return <span className="text-ink/90">{value}</span>;
  }
  const cell = value as Cell;
  if (!cell || typeof cell !== 'object') return <span className="text-faint">—</span>;
  if (cell.gap)
    return (
      <span className="chip border-gap/40 text-gap" title="Нет данных (пробел)">
        <CircleSlash size={11} /> пробел
      </span>
    );
  return (
    <span className="flex items-center gap-1.5">
      <span className="metric text-nickel-bright">
        {cell.value}
        {cell.unit ? ` ${cell.unit}` : ''}
      </span>
      {cell.evidence_ids && cell.evidence_ids.length > 0 && (
        <CircleCheck size={12} className="text-verified" />
      )}
    </span>
  );
}
