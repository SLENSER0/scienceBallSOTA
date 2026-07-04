import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  BadgeCheck,
  CircleCheck,
  CircleDashed,
  FileText,
  FlaskConical,
  GitBranch,
  Layers,
  Loader2,
  MessageSquare,
  Network,
  Play,
  Quote,
  Route,
  TriangleAlert,
  UploadCloud,
} from 'lucide-react';

// §22.6 «Непрерывный single-session демо-прогон всех 8 свойств целевой картины (§23)».
// Self-contained (no api.ts edits): drives POST /api/v1/demo/run and plays the eight
// returned chapters as one continuous, narrated walkthrough — question → plan → graph →
// evidence → gap → versioning → ingest-reflection — the «research intelligence, not a
// RAG bot» demo narrative. Backend router: routers/demo_run.py.

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

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

interface Chapter {
  index: number;
  propertyId: string;
  title: string;
  narrative: string;
  proven: boolean;
  data: Record<string, unknown>;
}
interface DemoRun {
  question: string;
  role: string;
  useLlm: boolean;
  chapters: Chapter[];
  summary: { propertiesProven: number; propertiesTotal: number; targetPictureAchieved: boolean };
}
interface QuestionsResponse {
  questions: { question: string; hint: string }[];
}

const ICONS: Record<string, typeof Network> = {
  'question-entry': MessageSquare,
  'agent-plan': Route,
  'answer-evidence': Quote,
  graph: Network,
  'edge-evidence': BadgeCheck,
  gaps: TriangleAlert,
  versioning: GitBranch,
  'ingest-reflection': UploadCloud,
};

function num(v: unknown): number {
  return typeof v === 'number' ? v : 0;
}
function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

// -- Per-chapter detail renderers -------------------------------------------

function KpiRow({ items }: { items: [string, string | number][] }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="panel p-2.5">
          <div className="font-display text-lg text-ink">{value}</div>
          <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
        </div>
      ))}
    </div>
  );
}

function ChapterDetail({ ch }: { ch: Chapter }) {
  const d = ch.data;
  switch (ch.propertyId) {
    case 'question-entry':
      return (
        <div className="panel p-3">
          <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">
            Вопрос в чат · роль {str(d.role)}
          </div>
          <div className="text-ink">«{str(d.question)}»</div>
        </div>
      );
    case 'agent-plan': {
      const steps = (d.steps as { tool: string; label: string; stage: string }[]) ?? [];
      return (
        <div className="space-y-2">
          <KpiRow
            items={[
              ['Интент', str(d.intent)],
              ['Уверенность', num(d.confidence).toFixed(2)],
              ['Инструментов', steps.length],
              ['Стадий', ((d.stagesTouched as string[]) ?? []).length],
            ]}
          />
          <div className="flex flex-wrap items-center gap-1.5">
            {steps.map((s, i) => (
              <span key={i} className="flex items-center gap-1.5">
                <span className="rounded bg-line/40 px-2 py-1 text-xs text-ink" title={s.stage}>
                  {s.tool}
                </span>
                {i < steps.length - 1 && <span className="text-faint">→</span>}
              </span>
            ))}
          </div>
        </div>
      );
    }
    case 'answer-evidence': {
      const w = (d.warnings as Record<string, number>) ?? {};
      const cites = (d.sampleCitations as { marker: string; sourceTitle: string; page: number }[]) ?? [];
      const conditions = (d.conditions as string[]) ?? [];
      return (
        <div className="space-y-2">
          <KpiRow
            items={[
              ['Чисел', num(d.numbersFound)],
              ['Источников', num(d.citationCount)],
              ['Пробелов', num(w.gaps)],
              ['Противоречий', num(w.contradictions)],
            ]}
          />
          {conditions.length > 0 && (
            <div className="text-xs text-faint">
              Условия: {conditions.map((c) => <span key={c} className="mr-1.5 text-ink">{c}</span>)}
            </div>
          )}
          <div className="panel max-h-40 overflow-y-auto whitespace-pre-wrap p-3 text-sm text-faint">
            {str(d.answerExcerpt)}…
          </div>
          {cites.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {cites.map((c) => (
                <span key={c.marker} className="rounded bg-line/40 px-2 py-1 text-xs text-ink">
                  {c.marker} {c.sourceTitle ?? '—'}
                  {c.page != null && <span className="text-faint"> · с.{c.page}</span>}
                </span>
              ))}
            </div>
          )}
        </div>
      );
    }
    case 'graph': {
      const kinds = (d.entityKinds as Record<string, number>) ?? {};
      const labelRu: Record<string, string> = {
        materials: 'материалы',
        regimes: 'режимы',
        experiments: 'эксперименты',
        properties: 'свойства',
        sources: 'источники',
      };
      return (
        <div className="space-y-2">
          <KpiRow
            items={[
              ['Узлов', num(d.nodeCount)],
              ['Рёбер', num(d.edgeCount)],
              ['Видов', `${num(d.kindsCovered)}/5`],
              ['Типов', ((d.presentTypes as string[]) ?? []).length],
            ]}
          />
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(kinds).map(([k, v]) => (
              <span
                key={k}
                className={`rounded px-2 py-1 text-xs ${
                  v > 0 ? 'bg-emerald-500/15 text-emerald-300' : 'bg-line/30 text-faint'
                }`}
              >
                {labelRu[k] ?? k}: {v}
              </span>
            ))}
          </div>
        </div>
      );
    }
    case 'edge-evidence': {
      const fact = d.factNode as { id: string; name: string; label: string } | null;
      const edge = d.edge as { type: string } | null;
      const ev = (d.evidence as { docId: string; page: number; text: string; evidenceId: string }[]) ?? [];
      return (
        <div className="space-y-2">
          {fact && (
            <div className="text-sm text-ink">
              Ребро{' '}
              <span className="rounded bg-line/40 px-1.5 py-0.5 text-xs">{edge?.type ?? 'SUPPORTED_BY'}</span>{' '}
              → факт <span className="text-copper">{fact.name ?? fact.id}</span>{' '}
              <span className="text-faint">({fact.label})</span>
            </div>
          )}
          {ev.map((e) => (
            <div key={e.evidenceId} className="panel p-3">
              <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wide text-faint">
                <FileText size={12} /> {e.docId} · с.{e.page}
              </div>
              <div className="text-sm text-ink">{e.text || '(span привязан; текст в источнике)'}</div>
            </div>
          ))}
        </div>
      );
    }
    case 'gaps': {
      const top = (d.topGaps as { id: string; name: string; domain: string; score: number; nextExperiment: string }[]) ?? [];
      return (
        <div className="space-y-2">
          <KpiRow
            items={[
              ['Всего Gap', num(d.totalGaps)],
              ['В ответе', num(d.gapsInAnswer)],
              ['Показано', top.length],
              ['First-class', 'Gap'],
            ]}
          />
          {top.slice(0, 4).map((g) => (
            <div key={g.id} className="panel p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">{g.name}</div>
                <span className="shrink-0 rounded bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">
                  {g.score.toFixed(2)}
                </span>
              </div>
              <div className="mt-1 flex items-start gap-1.5 text-xs text-faint">
                <FlaskConical size={13} className="mt-0.5 shrink-0 text-copper" />
                {g.nextExperiment}
              </div>
            </div>
          ))}
        </div>
      );
    }
    case 'versioning': {
      const labels = (d.labelCounts as Record<string, number>) ?? {};
      const runs = (d.runs as { id: string; name: string; kind: string }[]) ?? [];
      return (
        <div className="space-y-2">
          <KpiRow
            items={[
              ['ExtractorRun', num(labels.ExtractorRun)],
              ['GapScanRun', num(labels.GapScanRun)],
              ['Evidence', num(labels.Evidence)],
              ['confidence', num(d.nodesWithConfidence)],
            ]}
          />
          <div className="flex flex-wrap gap-1.5">
            {runs.map((r) => (
              <span key={r.id} className="flex items-center gap-1 rounded bg-line/40 px-2 py-1 text-xs text-ink">
                <Layers size={12} className="text-copper" /> {r.name} · {r.kind}
              </span>
            ))}
          </div>
        </div>
      );
    }
    case 'ingest-reflection': {
      const s = (d.surfaces as Record<string, Record<string, unknown>>) ?? {};
      const graph = s.graph ?? {};
      const idx = s.indexes ?? {};
      const cov = s.coverage ?? {};
      return (
        <div className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="panel p-3">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">Граф (Neo4j)</div>
              <div className="font-display text-lg text-ink">{num(graph.nodes).toLocaleString()}</div>
              <div className="text-xs text-faint">узлов · {num(graph.documents)} документов</div>
            </div>
            <div className="panel p-3">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">Индексы</div>
              <div className="font-display text-lg text-ink">{num(idx.chunksIndexed).toLocaleString()}</div>
              <div className="text-xs text-faint">чанков · Qdrant + OpenSearch</div>
            </div>
            <div className="panel p-3">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">Coverage</div>
              <div className="font-display text-lg text-ink">
                {cov.coverageRatio != null ? `${(num(cov.coverageRatio) * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="text-xs text-faint">
                {num(cov.covered)}/{num(cov.total)} ячеек
              </div>
            </div>
          </div>
          <div className="flex items-start gap-1.5 text-xs text-faint">
            <UploadCloud size={13} className="mt-0.5 shrink-0 text-copper" />
            {str(d.note)}
          </div>
        </div>
      );
    }
    default:
      return null;
  }
}

export function TargetPictureDemoView() {
  const [run, setRun] = useState<DemoRun | null>(null);
  const [question, setQuestion] = useState('');
  const [useLlm, setUseLlm] = useState(false);
  const [revealed, setRevealed] = useState(0); // chapters played so far (autoplay)
  const [active, setActive] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const questions = useQuery({
    queryKey: ['demo-questions'],
    queryFn: () => apiGet<QuestionsResponse>('/api/v1/demo/questions'),
  });

  const mut = useMutation({
    mutationFn: () =>
      apiPost<DemoRun>('/api/v1/demo/run', {
        question: question.trim() || null,
        use_llm: useLlm,
      }),
    onSuccess: (d) => {
      setRun(d);
      setRevealed(1);
      setActive(0);
    },
  });

  // Autoplay: reveal chapters one-by-one so the run reads as a continuous session.
  useEffect(() => {
    if (!run) return;
    if (revealed >= run.chapters.length) return;
    timer.current = setTimeout(() => {
      setRevealed((r) => r + 1);
      setActive(revealed); // follow the newest revealed chapter
    }, 1400);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [run, revealed]);

  const chapters = run?.chapters ?? [];
  const activeCh = chapters[active];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">§22.6 · целевая картина §23</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Демо-прогон целевой картины</h2>
        <p className="mb-4 max-w-3xl text-sm text-faint">
          Один непрерывный сценарий одной сессией демонстрирует все 8 свойств целевой картины
          подряд: вопрос → план агента → ответ с числами/источниками/предупреждениями → граф →
          доказательство под ребром → пробелы как объекты → версионирование → отражение нового
          документа в графе/индексах/coverage. «Research intelligence, не RAG-бот».
        </p>

        {/* Controls */}
        <div className="panel mb-5 space-y-3 p-4">
          <div className="flex flex-wrap gap-1.5">
            {questions.data?.questions.map((q) => (
              <button
                key={q.question}
                onClick={() => setQuestion(q.question)}
                title={q.hint}
                className={`rounded px-2.5 py-1 text-xs ${
                  question === q.question ? 'bg-copper/20 text-copper' : 'bg-line/40 text-faint hover:text-ink'
                }`}
              >
                {q.question.length > 46 ? q.question.slice(0, 46) + '…' : q.question}
              </button>
            ))}
          </div>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Научный вопрос (или выберите готовый выше)…"
            className="w-full rounded border border-line/60 bg-transparent px-3 py-2 text-sm text-ink outline-none focus:border-copper"
          />
          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-xs text-faint">
              <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
              Синтез через OSS-LLM (медленнее; по умолчанию детерминированно)
            </label>
            <button
              onClick={() => mut.mutate()}
              disabled={mut.isPending}
              className="btn-copper flex items-center gap-2"
            >
              {mut.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {mut.isPending ? 'Прогон…' : 'Запустить прогон'}
            </button>
          </div>
        </div>

        {mut.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка прогона: {(mut.error as Error).message}
          </div>
        )}

        {run && (
          <div className="space-y-4">
            {/* Verdict */}
            <div
              className={`panel flex items-center gap-3 p-4 ${
                run.summary.targetPictureAchieved ? 'border-emerald-500/40' : 'border-amber-500/40'
              }`}
            >
              {run.summary.targetPictureAchieved ? (
                <BadgeCheck size={28} className="text-emerald-400" />
              ) : (
                <TriangleAlert size={28} className="text-amber-400" />
              )}
              <div>
                <div className="font-display text-lg text-ink">
                  {run.summary.targetPictureAchieved
                    ? 'Целевая картина достигнута'
                    : 'Целевая картина частична'}
                </div>
                <div className="text-sm text-faint">
                  Доказано {run.summary.propertiesProven} из {run.summary.propertiesTotal} свойств
                  §23 на живом графе · «{run.question}»
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-[240px_1fr]">
              {/* Rail: the eight properties as a checklist */}
              <div className="space-y-1.5">
                {chapters.map((ch, i) => {
                  const Icon = ICONS[ch.propertyId] ?? Network;
                  const played = i < revealed;
                  return (
                    <button
                      key={ch.propertyId}
                      onClick={() => played && setActive(i)}
                      disabled={!played}
                      className={`flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-sm transition ${
                        i === active ? 'bg-copper/15 text-ink' : played ? 'text-faint hover:text-ink' : 'text-faint/40'
                      }`}
                    >
                      {!played ? (
                        <CircleDashed size={16} className="shrink-0 animate-pulse" />
                      ) : ch.proven ? (
                        <CircleCheck size={16} className="shrink-0 text-emerald-400" />
                      ) : (
                        <TriangleAlert size={16} className="shrink-0 text-amber-400" />
                      )}
                      <Icon size={14} className="shrink-0 opacity-70" />
                      <span className="truncate">
                        {ch.index}. {ch.title}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Active chapter */}
              {activeCh && active < revealed && (
                <div className="panel space-y-3 p-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-copper/20 px-2 py-0.5 text-xs text-copper">
                        Свойство {activeCh.index}/8
                      </span>
                      {activeCh.proven ? (
                        <span className="flex items-center gap-1 text-xs text-emerald-400">
                          <CircleCheck size={13} /> доказано
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-amber-400">
                          <TriangleAlert size={13} /> частично
                        </span>
                      )}
                    </div>
                    <h3 className="mt-1.5 font-display text-lg text-ink">{activeCh.title}</h3>
                    <p className="mt-0.5 text-sm text-faint">{activeCh.narrative}</p>
                  </div>
                  <ChapterDetail ch={activeCh} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
