import { useState } from 'react';
import { ArrowRight, HelpCircle, Loader2, Sparkles } from 'lucide-react';
import type { AnswerPayload } from '../types';
import { AnswerView } from './AnswerView';

// §13.21 «HITL-уточнение в чате»: agent stops and re-asks. Before answering, the
// backend scans the question for an *ambiguous critical entity* (near-tie graph
// candidates). If one is found the agent pauses and returns a clarification with
// options instead of guessing; the human picks, and the agent resumes on the
// disambiguated question — a live dialog rather than a silent best-guess.
//
// Self-contained on purpose: it calls the /api/v1/chat/clarify/* endpoints with a
// tiny inline fetch so it works the moment it is added to the nav, without editing
// api.ts. (Wiring notes still offer the canonical api.ts methods.)

interface Candidate {
  canonical_id: string;
  confidence: number;
  label: string | null;
  name: string;
}

interface ClarifyRequest {
  type: string;
  question: string;
  options: string[];
  context: { candidates?: Candidate[] };
}

type CheckResult =
  | { status: 'ok' }
  | { status: 'clarify'; clarify_id: string; mention: string; request: ClarifyRequest };

interface ResumeResult {
  status: 'answered';
  answer?: AnswerPayload;
  message_id?: string;
  stream_url?: string;
}

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

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

const EXAMPLES = [
  'Сравни свойства стали и сплава Al-Cu из меди',
  'Какие технологии переработки меди применяются на практике?',
];

export function HitlClarifyView() {
  const [q, setQ] = useState('');
  const [phase, setPhase] = useState<'idle' | 'checking' | 'clarify' | 'resuming' | 'done'>('idle');
  const [clarify, setClarify] = useState<Extract<CheckResult, { status: 'clarify' }> | null>(null);
  const [answer, setAnswer] = useState<AnswerPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setClarify(null);
    setAnswer(null);
    setError(null);
  };

  const submit = async (text: string) => {
    const content = text.trim();
    if (!content) return;
    reset();
    setPhase('checking');
    try {
      const result = await post<CheckResult>('/api/v1/chat/clarify/check', { content });
      if (result.status === 'clarify') {
        setClarify(result);
        setPhase('clarify');
      } else {
        // No ambiguity — the real app would post the message normally; here we say so.
        setPhase('done');
      }
    } catch (e) {
      setError(String(e));
      setPhase('idle');
    }
  };

  const choose = async (option: string) => {
    if (!clarify) return;
    setPhase('resuming');
    try {
      const result = await post<ResumeResult>('/api/v1/chat/clarify/resume', {
        clarify_id: clarify.clarify_id,
        resume_value: option,
      });
      setAnswer(result.answer ?? null);
      setPhase('done');
    } catch (e) {
      setError(String(e));
      setPhase('clarify');
    }
  };

  const busy = phase === 'checking' || phase === 'resuming';
  const candidates = clarify?.request.context.candidates ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto px-6 py-5">
      <div className="mx-auto w-full max-w-3xl space-y-5">
        <header className="space-y-1">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-nickel">
            <Sparkles size={18} className="text-copper" /> Уточнение в диалоге
          </h1>
          <p className="text-sm text-faint">
            Если в вопросе что-то можно понять двояко, ассистент остановится и переспросит — вместо того чтобы угадывать.
          </p>
        </header>

        <div className="panel p-1.5 shadow-panel focus-within:shadow-molten">
          <div className="flex items-end gap-2">
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit(q);
              }}
              rows={2}
              placeholder="Задайте вопрос, который можно понять по-разному…"
              className="min-h-[3rem] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-nickel outline-none placeholder:text-faint"
            />
            <button
              onClick={() => void submit(q)}
              disabled={busy || !q.trim()}
              className="mb-1 mr-1 flex items-center gap-1.5 rounded-lg bg-copper px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {phase === 'checking' ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
              Спросить
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => {
                setQ(ex);
                void submit(ex);
              }}
              className="rounded-full border border-white/10 px-3 py-1 text-xs text-faint hover:text-nickel"
            >
              {ex}
            </button>
          ))}
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        {phase === 'clarify' && clarify && (
          <section className="panel space-y-3 p-4">
            <div className="flex items-start gap-2">
              <HelpCircle size={18} className="mt-0.5 shrink-0 text-amber-400" />
              <div>
                <p className="text-sm font-medium text-nickel">{clarify.request.question}</p>
                <p className="mt-0.5 text-xs text-faint">
                  Неоднозначное упоминание: <span className="text-copper">«{clarify.mention}»</span>
                </p>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {candidates.map((c) => (
                <button
                  key={c.canonical_id}
                  onClick={() => void choose(c.canonical_id)}
                  disabled={phase !== 'clarify'}
                  className="group flex flex-col items-start gap-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-left hover:border-copper/50 hover:bg-copper/10 disabled:opacity-40"
                >
                  <span className="text-sm font-medium text-nickel group-hover:text-copper">{c.name}</span>
                  <span className="text-xs text-faint">
                    {c.label ?? 'Entity'} · {c.canonical_id}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {phase === 'resuming' && (
          <div className="flex items-center gap-2 text-sm text-faint">
            <Loader2 size={15} className="animate-spin" /> Продолжаю с выбранной сущностью…
          </div>
        )}

        {phase === 'done' && !answer && !clarify && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
            Сущность однозначна — уточнение не требуется, можно отвечать сразу.
          </div>
        )}

        {answer && (
          <section className="panel p-4">
            <AnswerView answer={answer} />
          </section>
        )}
      </div>
    </div>
  );
}
