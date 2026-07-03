import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
} from 'd3-force';
import { Camera, Maximize2, Minimize2, RotateCcw, Scan } from 'lucide-react';
import type { GraphNode, GraphResponse } from '../types';

// «Клубок» — canvas force-graph (§5.2.3). Canvas (not SVG) so thousands of
// nodes stay smooth: the sim redraws imperatively on tick, never through React.
// Interactions: drag a node (pins it), wheel-zoom, drag empty space to pan,
// double-click to unpin, fullscreen. Big subgraphs are sampled to MAX_NODES by
// degree so a 1000-node answer never freezes the tab.

type SimNode = GraphNode & {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
  deg: number;
  r: number;
};
type SimLink = {
  source: SimNode;
  target: SimNode;
  type: string;
  contradicted?: boolean | null;
  inferred?: boolean | null;
  confidence?: number | null;
  evidenceCount?: number | null;
};

const MAX_NODES = 600; // cap rendered nodes; keep the highest-degree ones
const TYPE_COLOR: Record<string, string> = {
  Material: '#8FA3B0',
  ChemicalElement: '#8FA3B0',
  TechnologySolution: '#C87941',
  Method: '#C87941',
  ProcessingRegime: '#E89B5C',
  Equipment: '#B9CAD4',
  Measurement: '#E89B5C',
  Property: '#8FA3B0',
  Evidence: '#5A6270',
  Paper: '#6C8CD5',
  Document: '#6C8CD5',
  Gap: '#E0A23C',
  Contradiction: '#E5484D',
  Person: '#B9CAD4',
  Lab: '#B9CAD4',
};

function colorFor(type: string): string {
  return TYPE_COLOR[type] ?? '#8FA3B0';
}
function radiusFor(n: GraphNode & { deg?: number }): number {
  return 5 + Math.min(7, (n.evidenceCount ?? 1) * 1.1 + (n.deg ?? 0) * 0.25);
}

export function GraphView({
  data,
  onSelect,
  selectedId,
}: {
  data: GraphResponse;
  onSelect?: (n: GraphNode) => void;
  selectedId?: string | null;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const adjRef = useRef<Map<string, Set<string>>>(new Map());
  const viewRef = useRef({ k: 1, x: 0, y: 0 }); // pan/zoom transform
  const dimsRef = useRef({ w: 640, h: 520 });
  const hoverRef = useRef<string | null>(null);
  const dragRef = useRef<{
    node: SimNode | null;
    panning: boolean;
    sx: number;
    sy: number;
    moved: boolean;
  }>({ node: null, panning: false, sx: 0, sy: 0, moved: false });

  const [full, setFull] = useState(false);
  const [shown, setShown] = useState({ n: 0, total: 0 });

  // ---- draw (imperative, reads refs; re-created only when selection changes) ----
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const { w, h } = dimsRef.current;
    const dpr = window.devicePixelRatio || 1;
    const { k, x: tx, y: ty } = viewRef.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.translate(tx, ty);
    ctx.scale(k, k);

    const hover = hoverRef.current;
    const near = hover ? adjRef.current.get(hover) : null;
    const lit = (id: string) => !near || id === hover || near.has(id);

    // edges
    for (const l of linksRef.current) {
      const dim = near && !(lit(l.source.id) && lit(l.target.id));
      ctx.beginPath();
      ctx.moveTo(l.source.x, l.source.y);
      ctx.lineTo(l.target.x, l.target.y);
      ctx.strokeStyle = l.contradicted ? '#E5484D' : '#C87941';
      const base = 0.6 + Math.min(2.2, (l.evidenceCount ?? 1) * 0.45);
      ctx.lineWidth = (l.contradicted ? base + 0.8 : base) / k;
      ctx.globalAlpha = dim ? 0.04 : 0.12 + Math.min(0.45, (l.confidence ?? 0.5) * 0.5);
      ctx.setLineDash(l.contradicted || l.inferred ? [4 / k, 3 / k] : []);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;

    // nodes
    for (const n of nodesRef.current) {
      const r = n.r;
      const dim = near ? !lit(n.id) : false;
      const selected = selectedId === n.id;
      const hollow = n.type === 'Gap' || (n.missingFields != null && n.missingFields.length > 0);
      const col = colorFor(n.type);
      const a = dim ? 0.22 : 1;
      if (selected) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 7, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(200,121,65,0.22)';
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      if (!hollow) {
        ctx.globalAlpha = a * (n.verified ? 1 : 0.78);
        ctx.fillStyle = col;
        ctx.fill();
      }
      ctx.globalAlpha = a;
      ctx.lineWidth = (hollow ? 1.6 : n.verified ? 2 : 0.6) / k;
      ctx.setLineDash(hollow ? [3 / k, 2 / k] : []);
      ctx.strokeStyle = col;
      ctx.stroke();
      ctx.setLineDash([]);
      if (n.verified) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 2.5, 0, 2 * Math.PI);
        ctx.strokeStyle = '#3FB68B';
        ctx.lineWidth = 0.9 / k;
        ctx.globalAlpha = a * 0.75;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if (hover === n.id || selected || (k > 1.7 && r >= 8)) {
        ctx.globalAlpha = dim ? 0.3 : 1;
        ctx.fillStyle = '#E9E6DF';
        ctx.font = `${(11 / k).toFixed(2)}px "IBM Plex Mono", monospace`;
        ctx.fillText(n.label.slice(0, 34), n.x + r + 4 / k, n.y + 4 / k);
        ctx.globalAlpha = 1;
      }
    }
  }, [selectedId]);

  // ---- (re)build graph + simulation when data changes ----
  useEffect(() => {
    const deg = new Map<string, number>();
    for (const e of data.edges) {
      deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
      deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    }
    const total = data.nodes.length;
    let picked = data.nodes.map((n) => ({ ...n, deg: deg.get(n.id) ?? 0 }));
    if (picked.length > MAX_NODES) {
      picked = [...picked].sort((a, b) => b.deg - a.deg).slice(0, MAX_NODES);
    }
    const keep = new Set(picked.map((n) => n.id));
    const { w, h } = dimsRef.current;
    const simNodes: SimNode[] = picked.map((n, i) => ({
      ...n,
      x: w / 2 + Math.cos(i) * 140,
      y: h / 2 + Math.sin(i) * 140,
      r: radiusFor(n),
    }));
    const nmap = new Map(simNodes.map((n) => [n.id, n]));
    const links: SimLink[] = [];
    const adj = new Map<string, Set<string>>();
    for (const e of data.edges) {
      if (!keep.has(e.source) || !keep.has(e.target)) continue;
      const s = nmap.get(e.source);
      const t = nmap.get(e.target);
      if (!s || !t) continue;
      links.push({
        source: s,
        target: t,
        type: e.type,
        contradicted: e.contradicted,
        inferred: e.inferred,
        confidence: e.confidence,
        evidenceCount: e.evidenceCount,
      });
      if (!adj.has(s.id)) adj.set(s.id, new Set());
      if (!adj.has(t.id)) adj.set(t.id, new Set());
      adj.get(s.id)!.add(t.id);
      adj.get(t.id)!.add(s.id);
    }
    nodesRef.current = simNodes;
    linksRef.current = links;
    adjRef.current = adj;
    viewRef.current = { k: 1, x: 0, y: 0 };
    setShown({ n: simNodes.length, total });

    simRef.current?.stop();
    const sim = forceSimulation<SimNode>(simNodes)
      .force('charge', forceManyBody<SimNode>().strength(-190))
      .force('link', forceLink<SimNode, SimLink>(links).distance(72).strength(0.35))
      .force('center', forceCenter(w / 2, h / 2))
      .force('collide', forceCollide<SimNode>().radius((d) => d.r + 6))
      .alpha(0.9)
      .alphaDecay(0.045)
      .on('tick', draw);
    simRef.current = sim;
    return () => {
      sim.stop();
    };
  }, [data, draw]);

  // ---- size to container (also handles fullscreen resize) ----
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const apply = (w: number, h: number) => {
      dimsRef.current = { w, h: Math.max(320, h) };
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(dimsRef.current.h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${dimsRef.current.h}px`;
      const c = simRef.current?.force('center') as ReturnType<typeof forceCenter> | undefined;
      c?.x(w / 2).y(dimsRef.current.h / 2);
      simRef.current?.alpha(0.3).restart();
      draw();
    };
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      apply(r.width, r.height);
    });
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [draw]);

  // ---- fullscreen ----
  useEffect(() => {
    const onFs = () => setFull(document.fullscreenElement === wrapRef.current);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);
  const toggleFull = useCallback(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void wrap.requestFullscreen?.();
  }, []);

  const fit = useCallback(() => {
    const ns = nodesRef.current;
    if (!ns.length) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of ns) {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
    }
    const { w, h } = dimsRef.current;
    const gw = Math.max(1, maxX - minX);
    const gh = Math.max(1, maxY - minY);
    const k = Math.min(6, Math.max(0.2, 0.85 * Math.min(w / gw, h / gh)));
    viewRef.current = {
      k,
      x: w / 2 - k * (minX + gw / 2),
      y: h / 2 - k * (minY + gh / 2),
    };
    draw();
  }, [draw]);

  const resetLayout = useCallback(() => {
    for (const n of nodesRef.current) {
      n.fx = null;
      n.fy = null;
    }
    viewRef.current = { k: 1, x: 0, y: 0 };
    simRef.current?.alpha(0.9).restart();
  }, []);

  // Export the current canvas as a PNG figure (§17.16).
  const savePng = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `klubok-graph-${new Date().toISOString().slice(0, 10)}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }, 'image/png');
  }, []);

  // ---- pointer interaction (drag node / pan / hover / wheel-zoom / dbl-unpin) ----
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const toGraph = (ev: PointerEvent | WheelEvent | MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const px = ev.clientX - rect.left;
      const py = ev.clientY - rect.top;
      const { k, x, y } = viewRef.current;
      return { px, py, gx: (px - x) / k, gy: (py - y) / k };
    };
    const hit = (gx: number, gy: number): SimNode | null => {
      let best: SimNode | null = null;
      let bd = Infinity;
      for (const n of nodesRef.current) {
        const d = Math.hypot(gx - n.x, gy - n.y);
        if (d <= n.r + 6 && d < bd) {
          bd = d;
          best = n;
        }
      }
      return best;
    };
    const onDown = (ev: PointerEvent) => {
      const { px, py, gx, gy } = toGraph(ev);
      const n = hit(gx, gy);
      dragRef.current = { node: n, panning: !n, sx: px, sy: py, moved: false };
      canvas.setPointerCapture(ev.pointerId);
      if (n) {
        n.fx = n.x;
        n.fy = n.y;
        simRef.current?.alphaTarget(0.2).restart();
      }
    };
    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current;
      const { px, py, gx, gy } = toGraph(ev);
      if (d.node) {
        d.node.fx = gx;
        d.node.fy = gy;
        d.moved = true;
        draw();
      } else if (d.panning) {
        viewRef.current.x += px - d.sx;
        viewRef.current.y += py - d.sy;
        d.sx = px;
        d.sy = py;
        d.moved = true;
        draw();
      } else {
        const h = hit(gx, gy);
        const id = h?.id ?? null;
        if (id !== hoverRef.current) {
          hoverRef.current = id;
          canvas.style.cursor = id ? 'pointer' : 'grab';
          draw();
        }
      }
    };
    const onUp = (ev: PointerEvent) => {
      const d = dragRef.current;
      if (d.node && !d.moved) {
        onSelect?.(d.node); // click = select; leave node unpinned
        d.node.fx = null;
        d.node.fy = null;
      }
      simRef.current?.alphaTarget(0);
      dragRef.current = { node: null, panning: false, sx: 0, sy: 0, moved: false };
      try {
        canvas.releasePointerCapture(ev.pointerId);
      } catch {
        /* ignore */
      }
    };
    const onDbl = (ev: MouseEvent) => {
      const { gx, gy } = toGraph(ev);
      const n = hit(gx, gy);
      if (n) {
        n.fx = null;
        n.fy = null;
        simRef.current?.alpha(0.5).restart();
      }
    };
    const onWheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const { px, py, gx, gy } = toGraph(ev);
      const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
      const k = Math.min(6, Math.max(0.2, viewRef.current.k * factor));
      viewRef.current = { k, x: px - gx * k, y: py - gy * k };
      draw();
    };
    canvas.style.cursor = 'grab';
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('dblclick', onDbl);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      canvas.removeEventListener('pointerdown', onDown);
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp);
      canvas.removeEventListener('dblclick', onDbl);
      canvas.removeEventListener('wheel', onWheel);
    };
  }, [draw, onSelect]);

  const empty = shown.n === 0;
  return (
    <div ref={wrapRef} className="relative h-full w-full bg-graphite/40">
      <canvas ref={canvasRef} className="block h-full w-full touch-none select-none" />
      {empty && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-faint font-mono text-sm">
          Граф появится после запроса
        </div>
      )}
      {/* toolbar */}
      <div className="absolute right-2 top-2 flex gap-1">
        <IconBtn title="Вписать в экран" onClick={fit}>
          <Scan size={15} />
        </IconBtn>
        <IconBtn title="Сбросить раскладку" onClick={resetLayout}>
          <RotateCcw size={15} />
        </IconBtn>
        <IconBtn title="Сохранить как PNG" onClick={savePng}>
          <Camera size={15} />
        </IconBtn>
        <IconBtn title={full ? 'Выйти из полноэкранного' : 'Во весь экран'} onClick={toggleFull}>
          {full ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </IconBtn>
      </div>
      {/* badges */}
      <div className="pointer-events-none absolute bottom-2 left-2 flex flex-col gap-1 font-mono text-[10px] text-faint">
        {shown.total > shown.n && (
          <span className="rounded bg-graphite/80 px-1.5 py-0.5 text-copper">
            показано {shown.n} из {shown.total} узлов (по связности)
          </span>
        )}
        {!empty && (
          <span className="rounded bg-graphite/70 px-1.5 py-0.5">
            тащи узел · колесо — масштаб · фон — панорама · 2× клик — открепить
          </span>
        )}
      </div>
    </div>
  );
}

function IconBtn({
  children,
  title,
  onClick,
}: {
  children: ReactNode;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="rounded border border-line bg-graphite/80 p-1.5 text-faint transition hover:text-copper"
    >
      {children}
    </button>
  );
}
