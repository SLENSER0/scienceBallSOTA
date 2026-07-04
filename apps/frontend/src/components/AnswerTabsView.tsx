import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle,
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  FlaskConical,
  Network,
  Quote,
  SearchX,
} from 'lucide-react';
import type { AnswerPayload, GraphEdge } from '../types';
import { useStore } from '../store';
import { GraphPanel } from './GraphPanel';

// §17.7 «Tabs ответа» (§5.2.2): структурирует богатый ответ агента по стрим-событиям
// в переключаемые вкладки [Summary][Experiments][Evidence][Graph][Gaps][Contradictions]
// вместо одной простыни. Каждая вкладка наполняется из соответствующей секции
// AnswerPayload (которая, в свою очередь, собирается из stream-событий §5.3:
//   token/reasoning → Summary, table → Experiments, evidence/citations → Evidence,
//   graph → Graph, gap → Gaps, edges c contradicted=true → Contradictions).
//
// Компонент — drop-in замена <AnswerView answer={…}/>: тот же контракт (одна пропа
// answer: AnswerPayload), но с таб-навигацией. Пустые вкладки помечаются и
// недоступны для клика, активная вкладка запоминается локально.

type TabId = 'summary' | 'experiments' | 'evidence' | 'graph' | 'gaps' | 'contradictions';

const PRACTICE_LABEL: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};
function practiceLabel(g: string): string {
  return PRACTICE_LABEL[g] ?? g;
}

// Edges the graph flagged as contradicted — the Contradictions tab merges these
// with the answer-level contradiction list so nothing gets lost between payloads.
function contradictedEdges(answer: AnswerPayload): GraphEdge[] {
  return (answer.graph?.edges ?? []).filter((e) => e.contradicted === true);
}

export function AnswerTabsView({
  answer,
  onOpenGraph,
}: {
  answer: AnswerPayload;
  // Optional handoff to the full Graph Explorer (see wiring): receives the graph
  // that populates this answer. When omitted the «Открыть в Graph Explorer» button
  // is hidden and the embedded snapshot remains the only graph surface.
  onOpenGraph?: (answer: AnswerPayload) => void;
}) {
  const setSelectedNode = useStore((s) => s.setSelectedNode);
  const conf = answer.confidence ?? 0;

  const graphNodes = answer.graph?.nodes ?? [];
  const badEdges = useMemo(() => contradictedEdges(answer), [answer]);
  const contradictionCount = answer.contradictions.length + badEdges.length;

  // Node id → label, for rendering contradicted edges as «A → B».
  const nodeLabel = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of graphNodes) m.set(n.id, n.label);
    return m;
  }, [graphNodes]);

  const tabs: { id: TabId; label: string; icon: React.ReactNode; count: number }[] = [
    { id: 'summary', label: 'Summary', icon: <FileText size={13} />, count: answer.answerMarkdown ? 1 : 0 },
    { id: 'experiments', label: 'Experiments', icon: <FlaskConical size={13} />, count: answer.table?.rows.length ?? 0 },
    { id: 'evidence', label: 'Evidence', icon: <Quote size={13} />, count: answer.citations.length },
    { id: 'graph', label: 'Graph', icon: <Network size={13} />, count: graphNodes.length },
    { id: 'gaps', label: 'Gaps', icon: <SearchX size={13} />, count: answer.gaps.length },
    {
      id: 'contradictions',
      label: 'Contradictions',
      icon: <AlertTriangle size={13} />,
      count: contradictionCount,
    },
  ];

  // First non-empty tab is the default active one (Summary almost always wins).
  const [active, setActive] = useState<TabId>(() => tabs.find((t) => t.count > 0)?.id ?? 'summary');

  return (
    <div className="mt-6 animate-rise">
      {/* Confidence + models — a stable header above the tab strip. */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
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
      </div>

      {/* Tab strip */}
      <div className="flex flex-wrap gap-1 border-b border-line">
        {tabs.map((t) => {
          const empty = t.count === 0;
          const on = active === t.id;
          return (
            <button
              key={t.id}
              disabled={empty}
              onClick={() => setActive(t.id)}
              title={empty ? 'нет данных для этой вкладки' : t.label}
              className={`-mb-px flex items-center gap-1.5 rounded-t-md border border-b-0 px-3 py-1.5 text-xs transition ${
                on
                  ? 'border-line bg-surface/60 text-copper'
                  : empty
                    ? 'cursor-not-allowed border-transparent text-faint/40'
                    : 'border-transparent text-faint hover:text-nickel'
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
              {t.count > 0 && (
                <span
                  className={`ml-0.5 rounded-full px-1.5 font-mono text-[10px] ${
                    on ? 'bg-copper/20 text-copper' : 'bg-line/60 text-faint'
                  }`}
                >
                  {t.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab panels */}
      <div className="rounded-b-md rounded-tr-md border border-t-0 border-line bg-surface/30 p-4">
        {active === 'summary' && (
          <div>
            {answer.reasoning && <ReasoningPanel text={answer.reasoning} />}
            <div className="md">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.answerMarkdown}</ReactMarkdown>
            </div>
          </div>
        )}

        {active === 'experiments' &&
          (answer.table && answer.table.rows.length > 0 ? (
            <div className="overflow-x-auto panel">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    {answer.table.columns.map((c) => (
                      <th
                        key={c}
                        className="px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wide text-faint"
                      >
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
          ) : (
            <Empty>Нет таблицы экспериментов/сравнения для этого ответа.</Empty>
          ))}

        {active === 'evidence' &&
          (answer.citations.length > 0 ? (
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
                      <span className="ml-2 font-mono text-[10px] text-faint">
                        {c.evidence.evidenceStrength}
                        {c.geography ? ` · ${practiceLabel(c.geography)}` : ''}
                        {c.year ? ` · ${c.year}` : ''}
                        {c.evidence.page ? ` · стр.${c.evidence.page}` : ''}
                        {c.asOf ? ` · актуал. ${c.asOf}` : ''}
                      </span>
                    </span>
                    <FileText size={13} className="mt-0.5 text-faint group-hover:text-copper" />
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <Empty>Нет прикреплённых источников.</Empty>
          ))}

        {active === 'graph' &&
          (graphNodes.length > 0 && answer.graph ? (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="eyebrow">
                  подграф ответа · {graphNodes.length} узлов · {answer.graph.edges.length} связей
                </span>
                {onOpenGraph && (
                  <button
                    onClick={() => onOpenGraph(answer)}
                    className="chip text-faint hover:border-copper/40 hover:text-copper"
                    title="Передать граф в Graph Explorer"
                  >
                    <Network size={12} /> Открыть в Graph Explorer
                  </button>
                )}
              </div>
              <div className="h-[420px] w-full overflow-hidden rounded-md border border-line bg-graphite/40">
                <GraphPanel
                  data={answer.graph}
                  onSelect={(n) => setSelectedNode(n)}
                />
              </div>
            </div>
          ) : (
            <Empty>Для этого ответа граф не построен.</Empty>
          ))}

        {active === 'gaps' &&
          (answer.gaps.length > 0 ? (
            <ul className="space-y-1.5 text-sm text-ink/85">
              {answer.gaps.map((g, i) => (
                <li key={i} className="flex items-start gap-2">
                  <SearchX size={14} className="mt-0.5 shrink-0 text-gap" />
                  <span>
                    {g.name}
                    {g.type && <span className="ml-1 font-mono text-[10px] text-faint">[{g.type}]</span>}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Пробелов в знаниях по этому вопросу не выявлено.</Empty>
          ))}

        {active === 'contradictions' &&
          (contradictionCount > 0 ? (
            <div className="space-y-4">
              {answer.contradictions.length > 0 && (
                <ul className="space-y-1.5 text-sm text-ink/85">
                  {answer.contradictions.map((c, i) => (
                    <li key={`c${i}`} className="flex items-start gap-2">
                      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-contradiction" />
                      <span>{c.name}</span>
                    </li>
                  ))}
                </ul>
              )}
              {badEdges.length > 0 && (
                <div>
                  <div className="eyebrow mb-1.5">Противоречивые связи графа</div>
                  <ul className="space-y-1.5 text-sm text-ink/85">
                    {badEdges.map((e) => (
                      <li key={e.id} className="flex items-start gap-2">
                        <AlertTriangle size={14} className="mt-0.5 shrink-0 text-contradiction" />
                        <span>
                          <span className="text-ink">{nodeLabel.get(e.source) ?? e.source}</span>
                          <span className="mx-1 font-mono text-[10px] text-contradiction">
                            —{e.label || e.type}→
                          </span>
                          <span className="text-ink">{nodeLabel.get(e.target) ?? e.target}</span>
                          {typeof e.confidence === 'number' && (
                            <span className="ml-2 font-mono text-[10px] text-faint">
                              conf {Math.round(e.confidence * 100)}%
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <Empty>Противоречий не обнаружено.</Empty>
          ))}
      </div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="py-6 text-center text-sm text-faint">{children}</div>;
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
