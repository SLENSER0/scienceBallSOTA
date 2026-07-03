import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Brain, Loader2, MessageSquarePlus, Network, Send } from 'lucide-react';
import { api, type ChatMessage, type ChatSession } from '../api';
import type { AnswerPayload } from '../types';
import { AnswerView } from './AnswerView';
import { GraphPanel } from './GraphPanel';

// «Диалог с клубком» — chat over the live §14.4 backend: sessions, streaming SSE
// answers, and each assistant turn rendered as the full evidence-first AnswerView
// (+ an inline graph toggle). The backend runs the LangGraph agent per message
// and the /stream endpoint replays the answer token-by-token (§5.3).

type ThreadItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'assistant'; id: string; payload: AnswerPayload }
  | { kind: 'streaming'; id: string; text: string; reasoning: string; thinking: boolean };

function toThread(msgs: ChatMessage[]): ThreadItem[] {
  const out: ThreadItem[] = [];
  for (const m of msgs) {
    if (m.role === 'assistant') {
      try {
        out.push({ kind: 'assistant', id: m.message_id, payload: JSON.parse(m.content) as AnswerPayload });
        continue;
      } catch {
        /* fall through to plain */
      }
    }
    out.push({ kind: 'user', id: m.message_id, text: m.content });
  }
  return out;
}

// Open the SSE stream; feed reasoning + token chunks to callbacks; resolve at `done`.
function streamAnswer(
  url: string,
  onToken: (t: string) => void,
  onReasoning: (t: string) => void,
): Promise<void> {
  return new Promise((resolve) => {
    const es = new EventSource(url);
    const stop = () => {
      es.close();
      resolve();
    };
    es.addEventListener('reasoning', (e) => {
      try {
        onReasoning(JSON.parse((e as MessageEvent).data).text ?? '');
      } catch {
        /* ignore */
      }
    });
    es.addEventListener('token', (e) => {
      try {
        onToken(JSON.parse((e as MessageEvent).data).text ?? '');
      } catch {
        /* ignore malformed frame */
      }
    });
    es.addEventListener('done', stop);
    es.onerror = stop; // server closes the stream after `done`
  });
}

export function ChatView() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sid, setSid] = useState<string | null>(null);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      setSessions((await api.listSessions()).sessions);
    } catch {
      /* backend may be warming up */
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thread]);

  const openSession = async (id: string) => {
    setSid(id);
    setThread(toThread((await api.getSession(id)).messages));
  };

  const newChat = () => {
    setSid(null);
    setThread([]);
    setInput('');
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    let cur = sid;
    if (!cur) {
      cur = (await api.createSession(text.slice(0, 48))).session_id;
      setSid(cur);
    }
    setInput('');
    setBusy(true);
    const streamId = `s${thread.length}-${text.length}`;
    setThread((t) => [
      ...t,
      { kind: 'user', id: `u${streamId}`, text },
      { kind: 'streaming', id: streamId, text: '', reasoning: '', thinking: true },
    ]);
    try {
      const { stream_url } = await api.postMessage(cur, text);
      await streamAnswer(
        stream_url,
        (chunk) =>
          setThread((t) =>
            t.map((m) =>
              m.id === streamId && m.kind === 'streaming'
                ? { ...m, text: m.text + chunk, thinking: false }
                : m,
            ),
          ),
        (r) =>
          setThread((t) =>
            t.map((m) =>
              m.id === streamId && m.kind === 'streaming' ? { ...m, reasoning: r } : m,
            ),
          ),
      );
      // swap the streamed text for the authoritative rich payloads
      setThread(toThread((await api.getSession(cur)).messages));
      void loadSessions();
    } catch (e) {
      setThread((t) =>
        t.map((m) =>
          m.id === streamId && m.kind === 'streaming'
            ? { ...m, thinking: false, text: `⚠ Ошибка: ${String(e)}` }
            : m,
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <div className="flex h-full min-h-0">
      {/* Sessions sidebar */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-graphite/40 md:flex">
        <button
          onClick={newChat}
          className="m-2 flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm text-nickel transition hover:border-copper/50 hover:text-copper"
        >
          <MessageSquarePlus size={15} /> Новый диалог
        </button>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => void openSession(s.session_id)}
              className={`mb-1 w-full truncate rounded px-2.5 py-2 text-left text-xs transition ${
                s.session_id === sid ? 'bg-copper/15 text-copper' : 'text-faint hover:bg-surface/60 hover:text-nickel'
              }`}
              title={s.title || s.session_id}
            >
              {s.title || 'без названия'}
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="px-2 py-4 text-center font-mono text-[11px] text-faint">пока нет диалогов</div>
          )}
        </div>
      </aside>

      {/* Thread + composer */}
      <section className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
          {thread.length === 0 && (
            <div className="mx-auto mt-16 max-w-lg text-center">
              <div className="eyebrow mb-2">Диалог с клубком знаний</div>
              <p className="text-sm text-faint">
                Спросите про метод, материал, режим или пробел — ассистент ответит с доказательной базой,
                графом связей и оценкой достоверности. Стриминг ответа в реальном времени.
              </p>
            </div>
          )}
          <div className="mx-auto max-w-3xl space-y-4">
            {thread.map((m) =>
              m.kind === 'user' ? (
                <UserBubble key={m.id} text={m.text} />
              ) : m.kind === 'streaming' ? (
                <StreamingBubble key={m.id} text={m.text} reasoning={m.reasoning} thinking={m.thinking} />
              ) : (
                <AssistantTurn key={m.id} payload={m.payload} />
              ),
            )}
          </div>
          <div ref={endRef} />
        </div>

        {/* Composer */}
        <div className="border-t border-line bg-graphite/50 p-3">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              rows={1}
              placeholder="Спросите ассистента…  (Enter — отправить, Shift+Enter — перенос)"
              className="max-h-40 min-h-[42px] flex-1 resize-none rounded-md border border-line bg-surface/60 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
            />
            <button
              onClick={() => void send()}
              disabled={busy || !input.trim()}
              className="flex h-[42px] items-center gap-2 rounded-md bg-copper/20 px-4 text-sm text-copper transition enabled:hover:bg-copper/30 disabled:opacity-40"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-copper/15 px-3.5 py-2.5 text-sm text-ink">
        {text}
      </div>
    </div>
  );
}

function StreamingBubble({
  text,
  reasoning,
  thinking,
}: {
  text: string;
  reasoning: string;
  thinking: boolean;
}) {
  return (
    <div className="panel px-4 py-3">
      {reasoning && (
        <div className="mb-2 rounded border border-line bg-graphite/40 px-3 py-2">
          <div className="mb-1 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-copper">
            <Brain size={11} /> рассуждение
          </div>
          <div className="max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted">
            {reasoning}
          </div>
        </div>
      )}
      {thinking && !text ? (
        <div className="flex items-center gap-2 font-mono text-xs text-faint">
          <Loader2 size={14} className="animate-spin text-copper" /> ассистент рассуждает по графу…
        </div>
      ) : (
        <div className="md">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-copper/70 align-middle" />
        </div>
      )}
    </div>
  );
}

function AssistantTurn({ payload }: { payload: AnswerPayload }) {
  const [showGraph, setShowGraph] = useState(false);
  const hasGraph = (payload.graph?.nodes?.length ?? 0) > 0;
  return (
    <div className="panel px-4 pb-4 pt-1">
      <AnswerView answer={payload} />
      {hasGraph && (
        <div className="mt-3">
          <button
            onClick={() => setShowGraph((v) => !v)}
            className="chip text-faint hover:border-copper/40 hover:text-copper"
          >
            <Network size={12} /> {showGraph ? 'Скрыть граф' : `Граф · ${payload.graph!.nodes.length} узлов`}
          </button>
          {showGraph && (
            <div className="mt-2 h-[420px] overflow-hidden rounded-md border border-line">
              <GraphPanel data={payload.graph!} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
