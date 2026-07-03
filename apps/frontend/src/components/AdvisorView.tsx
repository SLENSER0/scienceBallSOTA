import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowRight,
  Award,
  Bot,
  CircleAlert,
  Loader2,
  Sparkles,
  ThumbsUp,
  TriangleAlert,
} from 'lucide-react';
import { api } from '../api';
import type { AdvisorCandidate } from '../types';

// Agentic Technology Advisor — the platform doesn't just search, it REASONS: one agent
// per candidate technology (GLM-5.2, in parallel) scores fit against the user's
// constraints from that technology's own graph facts; a synthesis agent (DeepSeek)
// writes the recommendation. Cards stream in live as each agent finishes (SSE).

const GEO = [
  { id: 'all', label: 'Вся' },
  { id: 'russia', label: 'Отеч.' },
  { id: 'foreign', label: 'Заруб.' },
];
const EXAMPLES = [
  'методы обессоливания воды: сульфаты 300 мг/л, сухой остаток ≤1000 мг/дм³',
  'извлечение меди при флотации сульфидных руд выше 90%',
  'удаление SO2 из отходящих газов металлургического производства',
];

const PRACTICE: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
  unknown: '—',
};

type Phase = 'idle' | 'running' | 'done';

export function AdvisorView() {
  const [q, setQ] = useState('');
  const [geo, setGeo] = useState('all');
  const [phase, setPhase] = useState<Phase>('idle');
  const [constraints, setConstraints] = useState('');
  const [expected, setExpected] = useState(0);
  const [cards, setCards] = useState<AdvisorCandidate[]>([]);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const esRef = useRef<EventSource | null>(null);

  const run = (query: string) => {
    if (!query.trim()) return;
    esRef.current?.close();
    setPhase('running');
    setConstraints('');
    setExpected(0);
    setCards([]);
    setSummary('');
    setError('');

    const es = new EventSource(api.adviseStreamUrl(query.trim(), geo, 5));
    esRef.current = es;
    es.addEventListener('constraints', (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setConstraints(d.text ?? '');
      setExpected(d.candidates ?? 0);
    });
    es.addEventListener('candidate', (e) => {
      const c = JSON.parse((e as MessageEvent).data) as AdvisorCandidate;
      setCards((prev) => [...prev, c].sort((a, b) => b.fit_score - a.fit_score));
    });
    es.addEventListener('summary', (e) => {
      setSummary(JSON.parse((e as MessageEvent).data).text ?? '');
    });
    es.addEventListener('done', () => {
      setPhase('done');
      es.close();
    });
    es.addEventListener('error', (e) => {
      const msg = (e as MessageEvent).data
        ? JSON.parse((e as MessageEvent).data).message
        : 'поток прерван';
      setError(String(msg));
      setPhase('done');
      es.close();
    });
  };

  const pending = Math.max(0, expected - cards.length);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow mb-1">агентный советник · рекомендация технологий</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Bot size={22} className="text-copper" /> Что выбрать под ваши условия
        </h1>
        <p className="mt-1 text-sm text-faint">
          На каждую технологию-кандидата запускается отдельный агент-рассуждатель
          (<span className="font-mono text-copper">glm-5.2</span>), который оценивает соответствие
          строго по данным графа. Итог сводит агент-синтезатор. Карточки появляются в реальном
          времени по мере завершения агентов.
        </p>

        {/* Composer */}
        <div className="panel mt-4 p-1.5">
          <div className="flex items-end gap-2">
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run(q);
              }}
              rows={2}
              placeholder="Условия: материал + процесс + числа + география…"
              className="min-h-[48px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-ink placeholder:text-faint focus:outline-none"
            />
            <button
              onClick={() => run(q)}
              disabled={phase === 'running' || !q.trim()}
              className="btn-copper mb-1 mr-1 flex items-center gap-1.5"
            >
              {phase === 'running' ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Sparkles size={16} />
              )}
              Посоветовать
            </button>
          </div>
        </div>

        <div className="mt-2 flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wide text-faint">практика:</span>
          <div className="flex overflow-hidden rounded-md border border-line">
            {GEO.map((o) => (
              <button
                key={o.id}
                onClick={() => setGeo(o.id)}
                className={`px-2.5 py-1 text-[11px] transition ${
                  geo === o.id ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {phase === 'idle' && (
          <div className="mt-6">
            <div className="eyebrow mb-2">Примеры</div>
            <div className="flex flex-col gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => {
                    setQ(ex);
                    run(ex);
                  }}
                  className="rounded-md border border-line bg-surface/40 px-3 py-2.5 text-left text-sm text-muted hover:border-copper/40 hover:text-ink"
                >
                  <ArrowRight size={13} className="mr-2 inline text-faint" />
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {constraints && (
          <div className="mt-4 font-mono text-[11px] text-faint">
            распознано → {constraints}
            {expected > 0 && ` · агентов: ${expected}`}
          </div>
        )}

        {/* Summary (recommendation) */}
        {summary && (
          <div className="panel mt-4 border-copper/30 p-4">
            <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-copper">
              <Award size={12} /> рекомендация
            </div>
            <div className="md text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-md border border-contradiction/40 bg-contradiction/10 px-4 py-3 text-sm text-contradiction">
            {error}
          </div>
        )}

        {/* Ranked candidate cards */}
        <div className="mt-4 space-y-3">
          {cards.map((c, i) => (
            <CandidateCard key={c.id} c={c} rank={i + 1} />
          ))}
          {Array.from({ length: pending }).map((_, i) => (
            <div
              key={`pending-${i}`}
              className="panel flex items-center gap-2 p-3 font-mono text-xs text-faint"
            >
              <Loader2 size={14} className="animate-spin text-copper" /> агент оценивает
              технологию…
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function CandidateCard({ c, rank }: { c: AdvisorCandidate; rank: number }) {
  const tone = c.fit_score >= 60 ? '#3FB68B' : c.fit_score >= 30 ? '#E0A23C' : '#E5484D';
  return (
    <div className="panel p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-graphite font-mono text-xs text-faint">
          {rank}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink">{c.name}</span>
            <span className="chip text-faint">{PRACTICE[c.practice_type] ?? c.practice_type}</span>
            {c.model && (
              <span className="font-mono text-[10px] text-faint" title="агент-оценщик">
                {c.model}
              </span>
            )}
          </div>
          {c.verdict && <div className="mt-1 text-sm text-muted">{c.verdict}</div>}
        </div>
        {/* fit meter */}
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="metric text-lg" style={{ color: tone }}>
            {c.fit_score}%
          </span>
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full" style={{ width: `${c.fit_score}%`, background: tone }} />
          </div>
        </div>
      </div>

      {(c.supports.length > 0 || c.limitations.length > 0 || c.gaps.length > 0) && (
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <Facet icon={<ThumbsUp size={11} />} tone="text-verified" items={c.supports} label="за" />
          <Facet
            icon={<TriangleAlert size={11} />}
            tone="text-gap"
            items={c.limitations}
            label="ограничения"
          />
          <Facet icon={<CircleAlert size={11} />} tone="text-contradiction" items={c.gaps} label="пробелы" />
        </div>
      )}
    </div>
  );
}

function Facet({
  icon,
  tone,
  items,
  label,
}: {
  icon: React.ReactNode;
  tone: string;
  items: string[];
  label: string;
}) {
  if (!items.length) return <div />;
  return (
    <div>
      <div className={`mb-1 flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide ${tone}`}>
        {icon} {label}
      </div>
      <ul className="space-y-0.5">
        {items.slice(0, 3).map((s, i) => (
          <li key={i} className="text-[12px] leading-snug text-ink/80">
            {s}
          </li>
        ))}
      </ul>
    </div>
  );
}
