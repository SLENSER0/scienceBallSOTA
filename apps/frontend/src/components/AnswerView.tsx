import { useState, Children, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AlertTriangle, Brain, ChevronDown, ChevronRight, Download, FileText, SearchX } from 'lucide-react';
import type { AnswerPayload } from '../types';
import { useStore } from '../store';

// Practice-type → short RU label for the отечественная/зарубежная distinction.
const PRACTICE_LABEL: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};
function practiceLabel(g: string): string {
  return PRACTICE_LABEL[g] ?? g;
}

// Turn inline «[n]» citation markers inside rendered markdown text into clickable
// chips that open the matching source in the evidence drawer («по ним переходить»).
function renderWithCites(children: ReactNode, onCite: (marker: string) => void): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== 'string') return child;
    return child.split(/(\[\d{1,3}\])/g).map((seg, i) => {
      if (!/^\[\d{1,3}\]$/.test(seg)) return seg;
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCite(seg)}
          title="открыть источник"
          className="mx-0.5 inline rounded bg-copper/15 px-1 align-baseline font-mono text-[11px] text-copper transition hover:bg-copper/30"
        >
          {seg}
        </button>
      );
    });
  });
}

export function AnswerView({ answer }: { answer: AnswerPayload }) {
  const setSelectedNode = useStore((s) => s.setSelectedNode);
  const conf = answer.confidence ?? 0;

  // Open the cited source (by its «[n]» marker) in the evidence drawer.
  const openCite = (marker: string) => {
    const c = answer.citations.find((x) => x.marker === marker);
    if (!c) return;
    setSelectedNode({
      id: c.evidence.evidenceId,
      label: c.sourceTitle ?? c.evidence.text ?? marker,
      type: 'Evidence',
      properties: c.evidence as unknown as Record<string, unknown>,
    });
  };
  const mdComponents = {
    p: ({ children }: { children?: ReactNode }) => <p>{renderWithCites(children, openCite)}</p>,
    li: ({ children }: { children?: ReactNode }) => <li>{renderWithCites(children, openCite)}</li>,
  };

  return (
    <div className="mt-6 animate-rise">
      {/* Reasoning trace (reasoning-capable OSS models) — collapsible «thinking». */}
      {answer.reasoning && <ReasoningPanel text={answer.reasoning} />}

      {/* Confidence + models */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ConfidenceMeter value={conf} />
        {answer.usedModels.length > 0 ? (
          answer.usedModels.map((m) => (
            <span key={m} className="chip text-copper-bright" title="OSS-модель (Apache-2.0 / MIT)">
              {m}
            </span>
          ))
        ) : (
          <span className="chip text-faint">детерминированный синтез</span>
        )}
        <ExportButtons query={(answer.parsedQuery?.raw as string) ?? ''} />
      </div>

      {/* Markdown answer — inline [n] markers are clickable → open the source drawer */}
      <div className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {answer.answerMarkdown}
        </ReactMarkdown>
      </div>

      {/* Comparison table */}
      {answer.table && answer.table.rows.length > 0 && (
        <div className="mt-5">
          <div className="eyebrow mb-2">Сравнение решений</div>
          <div className="overflow-x-auto panel">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  {answer.table.columns.map((c) => (
                    <th key={c} className="px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wide text-faint">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {answer.table.rows.map((row, i) => (
                  <tr key={i} className="border-t border-line/60">
                    {answer.table!.columns.map((c) => (
                      <td key={c} className="px-3 py-2 align-top text-ink/90">
                        {row[c]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Contradictions + gaps */}
      {(answer.contradictions.length > 0 || answer.gaps.length > 0) && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {answer.contradictions.length > 0 && (
            <Card icon={<AlertTriangle size={14} />} tone="contradiction" title="Противоречия">
              {answer.contradictions.map((c, i) => (
                <li key={i}>{c.name}</li>
              ))}
            </Card>
          )}
          {answer.gaps.length > 0 && (
            <Card icon={<SearchX size={14} />} tone="gap" title="Пробелы в знаниях">
              {answer.gaps.map((g, i) => (
                <li key={i}>
                  {g.name}
                  {g.type && <span className="ml-1 font-mono text-[10px] text-faint">[{g.type}]</span>}
                </li>
              ))}
            </Card>
          )}
        </div>
      )}

      {/* Citations */}
      {answer.citations.length > 0 && (
        <div className="mt-5">
          <div className="eyebrow mb-2">Источники · доказательная база</div>
          <ol className="space-y-1.5">
            {answer.citations.map((c) => (
              <li key={c.marker}>
                <button
                  onClick={() =>
                    setSelectedNode({
                      id: c.evidence.evidenceId,
                      label: c.sourceTitle ?? c.evidence.text ?? c.marker,
                      type: 'Evidence',
                      properties: c.evidence as unknown as Record<string, unknown>,
                    })
                  }
                  className="group flex w-full items-start gap-2 rounded border border-transparent px-2 py-1.5 text-left text-sm hover:border-line hover:bg-surface/50"
                >
                  <span className="metric mt-0.5 text-copper">{c.marker}</span>
                  <span className="flex-1 text-muted group-hover:text-ink">
                    {c.sourceTitle || c.evidence.text?.slice(0, 90) || 'источник'}
                    {c.evidence.tableId && (
                      <span
                        className="ml-1.5 rounded bg-copper/15 px-1 py-0.5 font-mono text-[9px] uppercase tracking-wide text-copper"
                        title={`табличная ячейка ${c.evidence.tableId}${c.evidence.rowIndex != null ? ` · строка ${c.evidence.rowIndex}` : ''}${c.evidence.colIndex != null ? ` · столбец ${c.evidence.colIndex}` : ''}`}
                      >
                        таблица
                      </span>
                    )}
                    <span className="ml-2 font-mono text-[10px] text-faint">
                      {c.evidence.evidenceStrength}
                      {c.geography ? ` · ${practiceLabel(c.geography)}` : ''}
                      {c.year ? ` · ${c.year}` : ''}
                      {c.evidence.page ? ` · стр.${c.evidence.page}` : ''}
                      {c.asOf ? ` · актуал. ${c.asOf}` : ''}
                    </span>
                    {(c.publicationDate || c.ingestionDate || c.lastVerifiedAt) && (
                      <span className="mt-0.5 block font-mono text-[10px] text-faint">
                        {[
                          c.publicationDate ? `публикация ${c.publicationDate}` : null,
                          c.ingestionDate ? `загружено ${c.ingestionDate}` : null,
                          c.lastVerifiedAt ? `проверено ${c.lastVerifiedAt}` : null,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    )}
                  </span>
                  <FileText size={13} className="mt-0.5 text-faint group-hover:text-copper" />
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function ReasoningPanel({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-4 rounded-md border border-line bg-graphite/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs text-faint transition hover:text-nickel"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Brain size={13} className="text-copper" />
        Рассуждение модели
        <span className="ml-auto font-mono text-[10px] text-faint">{text.length} симв.</span>
      </button>
      {open && (
        <div className="max-h-64 overflow-y-auto whitespace-pre-wrap border-t border-line px-3 py-2 font-mono text-[11px] leading-relaxed text-muted">
          {text}
        </div>
      )}
    </div>
  );
}

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = value >= 0.7 ? '#3FB68B' : value >= 0.45 ? '#E0A23C' : '#E5484D';
  return (
    <div className="flex items-center gap-2" title="Уровень достоверности ответа">
      <span className="eyebrow">достоверность</span>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: tone }} />
      </div>
      <span className="metric text-xs" style={{ color: tone }}>
        {pct}%
      </span>
    </div>
  );
}

function ExportButtons({ query }: { query: string }) {
  const dl = async (format: string) => {
    const res = await fetch('/api/v1/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, format, use_llm: false }),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report.${format === 'markdown' ? 'md' : format === 'jsonld' ? 'jsonld' : 'json'}`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="ml-auto flex gap-1">
      {['markdown', 'jsonld'].map((f) => (
        <button
          key={f}
          onClick={() => dl(f)}
          className="chip text-faint hover:border-copper/40 hover:text-copper"
          title={`Экспорт в ${f}`}
        >
          <Download size={11} />
          {f === 'markdown' ? 'MD' : 'JSON-LD'}
        </button>
      ))}
    </div>
  );
}

function Card({
  icon,
  tone,
  title,
  children,
}: {
  icon: React.ReactNode;
  tone: 'contradiction' | 'gap';
  title: string;
  children: React.ReactNode;
}) {
  const color = tone === 'contradiction' ? 'text-contradiction' : 'text-gap';
  const border = tone === 'contradiction' ? 'border-contradiction/30' : 'border-gap/30';
  return (
    <div className={`rounded-md border ${border} bg-surface/50 p-3`}>
      <div className={`mb-1.5 flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide ${color}`}>
        {icon}
        {title}
      </div>
      <ul className="space-y-1 text-sm text-ink/85">{children}</ul>
    </div>
  );
}
