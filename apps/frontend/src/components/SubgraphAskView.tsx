import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  BrainCircuit,
  Lasso,
  Loader2,
  MousePointerSquareDashed,
  Send,
  Trash2,
} from 'lucide-react';
import { api } from '../api';
import type { AnswerPayload, GraphNode, GraphResponse } from '../types';

// Lasso/box-выделение подграфа → «спросить агента о выделенном» (§17.8, §5.2.3).
// Тяни рамку по canvas (или кликай узлы) — выделяешь кластер сущностей; кнопка
// собирает node_ids и грунтует агента ИМЕННО на этом подграфе (POST
// /api/v1/subgraph-ask), ответ рендерится справа как обычный ответ ассистента.
// Seed-граф — живой Neo4j через api.gdsColoredGraph (тот же, что LiveGDS §3.14).

const TYPE_COLORS: Record<string, string> = {
  Material: '#C87941',
  Property: '#6C8CD5',
  Technology: '#5F9E7F',
  Process: '#5F9E7F',
  Regime: '#E0A23C',
  Measurement: '#B072C4',
  Source: '#8FA3B0',
  Finding: '#4FA6B8',
};

function typeColor(t: string): string {
  return TYPE_COLORS[t] ?? '#8FA3B0';
}

// -- self-contained auth+POST (мы не правим hub-файл api.ts) ------------------
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

interface SubgraphAskResult {
  answer: AnswerPayload;
  subgraph: GraphResponse;
  focus: {
    selected: number;
    node_count: number;
    edge_count: number;
    expand: number;
    entity_types: Record<string, number>;
    question: string;
  };
}

async function askSubgraph(
  nodeIds: string[],
  question: string,
  expand: number,
): Promise<SubgraphAskResult> {
  const res = await fetch('/api/v1/subgraph-ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ node_ids: nodeIds, question, expand }),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = String(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<SubgraphAskResult>;
}

type SimNode = GraphNode & { x: number; y: number; vx?: number; vy?: number; r: number };

export function SubgraphAskView() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [question, setQuestion] = useState('');
  const [expand, setExpand] = useState(0);
  const [result, setResult] = useState<SubgraphAskResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  const seed = useQuery({
    queryKey: ['subgraph-ask-seed'],
    queryFn: () => api.gdsColoredGraph(300),
    staleTime: 5 * 60_000,
  });
  const graph = seed.data;

  const nameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of graph?.nodes ?? []) m.set(n.id, n.label || n.id);
    return m;
  }, [graph]);

  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const id of selected) {
      const t = graph?.nodes.find((n) => n.id === id)?.type ?? 'Entity';
      c[t] = (c[t] ?? 0) + 1;
    }
    return c;
  }, [selected, graph]);

  const toggleNode = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const clearSel = () => setSelected(new Set());

  const runAsk = async () => {
    if (selected.size === 0 || asking) return;
    setAsking(true);
    setAskError(null);
    setResult(null);
    try {
      const r = await askSubgraph([...selected], question, expand);
      setResult(r);
    } catch (e) {
      setAskError(e instanceof Error ? e.message : String(e));
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="flex h-full min-h-0">
      {/* Canvas + lasso */}
      <div className="flex min-w-0 flex-1 flex-col border-r border-line">
        <div className="border-b border-line px-5 py-4">
          <div className="eyebrow mb-1">выделите и спросите</div>
          <h1 className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
            <Lasso size={18} className="text-copper" /> Выдели подграф — задай вопрос
          </h1>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-faint">
            <MousePointerSquareDashed size={13} /> Тяни рамку по полю или кликай узлы — выделишь кластер. Затем «Спросить» — ответ строится именно по выделенному.
          </p>
        </div>
        <div className="relative min-h-0 flex-1">
          {seed.isLoading ? (
            <div className="flex h-full items-center justify-center font-mono text-sm text-faint">
              <Loader2 size={15} className="mr-2 animate-spin text-copper" /> загрузка живого графа…
            </div>
          ) : seed.isError ? (
            <div className="flex h-full items-center justify-center px-6 text-center font-mono text-[11px] text-contradiction">
              граф недоступен
            </div>
          ) : graph && graph.nodes.length > 0 ? (
            <SelectCanvas graph={graph} selected={selected} onToggle={toggleNode} onBox={setSelected} />
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-[11px] text-faint">
              граф пуст
            </div>
          )}
        </div>
      </div>

      {/* Selection + answer */}
      <div className="flex w-[440px] shrink-0 flex-col">
        <div className="border-b border-line px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-ink">Выделено: {selected.size}</span>
            {selected.size > 0 && (
              <button
                onClick={clearSel}
                className="chip ml-auto flex items-center gap-1 text-faint hover:text-contradiction"
              >
                <Trash2 size={11} /> очистить
              </button>
            )}
          </div>
          {selected.size > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {Object.entries(typeCounts).map(([t, n]) => (
                <span key={t} className="chip flex items-center gap-1 text-[10px]">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: typeColor(t) }} />
                  {t}: {n}
                </span>
              ))}
            </div>
          )}
          {selected.size > 0 && (
            <div className="mt-2 max-h-24 overflow-y-auto">
              <div className="flex flex-wrap gap-1">
                {[...selected].slice(0, 40).map((id) => (
                  <button
                    key={id}
                    onClick={() => toggleNode(id)}
                    title="убрать из выделения"
                    className="chip text-[10px] text-muted hover:text-contradiction"
                  >
                    {nameById.get(id) ?? id}
                  </button>
                ))}
                {selected.size > 40 && (
                  <span className="chip text-[10px] text-faint">+{selected.size - 40}</span>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="border-b border-line px-5 py-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Необязательный вопрос о выделенном (если пусто — общий разбор)"
            rows={2}
            className="w-full resize-none rounded-md border border-line bg-surface/50 px-3 py-2 text-sm text-ink outline-none focus:border-copper/60"
          />
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-[11px] text-faint">
              контекст соседей
              <select
                value={expand}
                onChange={(e) => setExpand(Number(e.target.value))}
                className="rounded border border-line bg-surface/50 px-1.5 py-0.5 text-[11px] text-ink"
              >
                <option value={0}>только выделенное</option>
                <option value={1}>+1 шаг</option>
                <option value={2}>+2 шага</option>
              </select>
            </label>
            <button
              onClick={runAsk}
              disabled={selected.size === 0 || asking}
              className="ml-auto flex items-center gap-1.5 rounded-md bg-copper px-3 py-1.5 text-sm font-medium text-graphite disabled:opacity-40"
            >
              {asking ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              Спросить
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {askError && (
            <div className="rounded-md border border-contradiction/40 bg-contradiction/5 px-3 py-2 font-mono text-[11px] text-contradiction">
              {askError}
            </div>
          )}
          {!result && !asking && !askError && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center font-mono text-[11px] text-faint">
              <BrainCircuit size={22} className="text-faint/60" />
              выдели кластер узлов и задай вопрос — ответ будет о нём
            </div>
          )}
          {asking && (
            <div className="flex items-center gap-2 font-mono text-sm text-faint">
              <Loader2 size={15} className="animate-spin text-copper" /> Готовим ответ по выделенному…
            </div>
          )}
          {result && <AnswerBlock result={result} />}
        </div>
      </div>
    </div>
  );
}

function AnswerBlock({ result }: { result: SubgraphAskResult }) {
  const { answer, focus } = result;
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        <span className="chip text-[10px] text-copper">{focus.node_count} узлов</span>
        <span className="chip text-[10px] text-faint">{focus.edge_count} связей</span>
        {focus.expand > 0 && (
          <span className="chip text-[10px] text-faint">+{focus.expand} шаг соседей</span>
        )}
        {answer.confidence != null && (
          <span className="chip text-[10px] text-faint">
            уверенность {Math.round((answer.confidence ?? 0) * 100)}%
          </span>
        )}
      </div>
      <div className="prose-answer text-sm leading-relaxed text-ink">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.answerMarkdown}</ReactMarkdown>
      </div>
      {answer.citations && answer.citations.length > 0 && (
        <div className="mt-4">
          <div className="eyebrow mb-1.5">Источники</div>
          <ul className="space-y-1">
            {answer.citations.map((c, i) => (
              <li key={i} className="flex gap-1.5 text-[11px] text-muted">
                <span className="shrink-0 font-mono text-copper">{c.marker}</span>
                <span className="truncate">{c.sourceTitle || c.evidence?.text || c.evidence?.evidenceId}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.gaps && answer.gaps.length > 0 && (
        <div className="mt-4">
          <div className="eyebrow mb-1.5">Пробелы</div>
          <div className="flex flex-wrap gap-1">
            {answer.gaps.slice(0, 12).map((g, i) => (
              <span key={i} className="chip text-[10px] text-gap">
                {g.name ?? g.type ?? 'пробел'}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Canvas with box (lasso) selection --------------------------------------
function SelectCanvas({
  graph,
  selected,
  onToggle,
  onBox,
}: {
  graph: GraphResponse;
  selected: Set<string>;
  onToggle: (id: string) => void;
  onBox: (ids: Set<string>) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const selRef = useRef<Set<string>>(selected);
  const dragRef = useRef<{ x0: number; y0: number; x1: number; y1: number; moved: boolean } | null>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  selRef.current = selected;

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const { nodes, links } = useMemo(() => {
    const byId = new Map<string, SimNode>();
    const ns: SimNode[] = graph.nodes.map((n) => {
      const sn: SimNode = { ...n, x: Math.random() * 600, y: Math.random() * 400, r: 5 };
      byId.set(n.id, sn);
      return sn;
    });
    const ls: { source: SimNode; target: SimNode }[] = [];
    for (const e of graph.edges) {
      const s = byId.get(e.source);
      const t = byId.get(e.target);
      if (s && t) ls.push({ source: s, target: t });
    }
    const deg = new Map<string, number>();
    for (const l of ls) {
      deg.set(l.source.id, (deg.get(l.source.id) ?? 0) + 1);
      deg.set(l.target.id, (deg.get(l.target.id) ?? 0) + 1);
    }
    for (const n of ns) n.r = 4 + Math.min(8, deg.get(n.id) ?? 0);
    nodesRef.current = ns;
    return { nodes: ns, links: ls };
  }, [graph]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    if (!ctx) return;
    const { w, h } = size;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    let raf = 0;
    // Lightweight force layout (Verlet-ish); keeps deps minimal & stable.
    const linkDist = 60;
    const step = () => {
      // repulsion (O(n^2) — capped node count keeps this cheap on 300 nodes)
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.vx = (a.vx ?? 0) * 0.85;
        a.vy = (a.vy ?? 0) * 0.85;
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) {
            dx = Math.random() - 0.5;
            dy = Math.random() - 0.5;
            d2 = 1;
          }
          const f = 900 / d2;
          const d = Math.sqrt(d2);
          a.vx! += (dx / d) * f;
          a.vy! += (dy / d) * f;
          b.vx! -= (dx / d) * f;
          b.vy! -= (dy / d) * f;
        }
      }
      // springs
      for (const l of links) {
        const dx = l.target.x - l.source.x;
        const dy = l.target.y - l.source.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (d - linkDist) * 0.02;
        l.source.vx! += (dx / d) * f;
        l.source.vy! += (dy / d) * f;
        l.target.vx! -= (dx / d) * f;
        l.target.vy! -= (dy / d) * f;
      }
      // integrate + gentle centering
      for (const n of nodes) {
        n.vx! += (w / 2 - n.x) * 0.002;
        n.vy! += (h / 2 - n.y) * 0.002;
        n.x += Math.max(-8, Math.min(8, n.vx!));
        n.y += Math.max(-8, Math.min(8, n.vy!));
        n.x = Math.max(n.r, Math.min(w - n.r, n.x));
        n.y = Math.max(n.r, Math.min(h - n.r, n.y));
      }
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = 'rgba(143,163,176,0.22)';
      ctx.lineWidth = 1;
      for (const l of links) {
        ctx.beginPath();
        ctx.moveTo(l.source.x, l.source.y);
        ctx.lineTo(l.target.x, l.target.y);
        ctx.stroke();
      }
      const sel = selRef.current;
      for (const n of nodes) {
        const isSel = sel.has(n.id);
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = typeColor(n.type);
        ctx.globalAlpha = isSel ? 1 : 0.7;
        ctx.fill();
        if (isSel) {
          ctx.globalAlpha = 1;
          ctx.lineWidth = 2.5;
          ctx.strokeStyle = '#E8B778';
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r + 3, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
      // selection rectangle
      const dr = dragRef.current;
      if (dr && dr.moved) {
        const x = Math.min(dr.x0, dr.x1);
        const y = Math.min(dr.y0, dr.y1);
        ctx.strokeStyle = '#E8B778';
        ctx.setLineDash([4, 3]);
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, Math.abs(dr.x1 - dr.x0), Math.abs(dr.y1 - dr.y0));
        ctx.fillStyle = 'rgba(232,183,120,0.08)';
        ctx.fillRect(x, y, Math.abs(dr.x1 - dr.x0), Math.abs(dr.y1 - dr.y0));
        ctx.setLineDash([]);
      }
    };

    let ticks = 0;
    const loop = () => {
      if (ticks < 300) {
        step();
        ticks++;
      }
      draw();
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => cancelAnimationFrame(raf);
  }, [nodes, links, size]);

  // pointer handlers for box-select / click-toggle
  const localPos = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onDown = (e: React.MouseEvent) => {
    const p = localPos(e);
    dragRef.current = { x0: p.x, y0: p.y, x1: p.x, y1: p.y, moved: false };
  };
  const onMove = (e: React.MouseEvent) => {
    const dr = dragRef.current;
    if (!dr) return;
    const p = localPos(e);
    dr.x1 = p.x;
    dr.y1 = p.y;
    if (Math.abs(dr.x1 - dr.x0) + Math.abs(dr.y1 - dr.y0) > 4) dr.moved = true;
  };
  const onUp = (e: React.MouseEvent) => {
    const dr = dragRef.current;
    dragRef.current = null;
    if (!dr) return;
    const p = localPos(e);
    if (!dr.moved) {
      // click: toggle nearest node within its radius
      let hit: SimNode | null = null;
      let best = Infinity;
      for (const n of nodesRef.current) {
        const d = (n.x - p.x) ** 2 + (n.y - p.y) ** 2;
        if (d < best && d <= (n.r + 4) ** 2) {
          best = d;
          hit = n;
        }
      }
      if (hit) onToggle(hit.id);
      return;
    }
    // box: additive select of nodes inside rectangle
    const x0 = Math.min(dr.x0, dr.x1);
    const x1 = Math.max(dr.x0, dr.x1);
    const y0 = Math.min(dr.y0, dr.y1);
    const y1 = Math.max(dr.y0, dr.y1);
    const next = new Set(selRef.current);
    for (const n of nodesRef.current) {
      if (n.x >= x0 && n.x <= x1 && n.y >= y0 && n.y <= y1) next.add(n.id);
    }
    onBox(next);
  };

  return (
    <div ref={wrapRef} className="absolute inset-0">
      <canvas
        ref={canvasRef}
        className="h-full w-full cursor-crosshair"
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={() => (dragRef.current = null)}
      />
      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-line bg-graphite/70 px-2.5 py-1.5 font-mono text-[10px] text-faint">
        рамка = выделить область · клик = добавить/убрать узел
      </div>
    </div>
  );
}
