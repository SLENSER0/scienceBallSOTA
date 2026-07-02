import { useEffect, useMemo, useRef, useState } from 'react';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
} from 'd3-force';
import type { GraphNode, GraphResponse } from '../types';

type SimNode = GraphNode & { x: number; y: number; vx?: number; vy?: number; fx?: number | null; fy?: number | null };
type SimLink = { source: SimNode; target: SimNode; type: string; contradicted?: boolean | null };

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

function colorFor(n: GraphNode): string {
  return TYPE_COLOR[n.type] ?? '#8FA3B0';
}
function radiusFor(n: GraphNode): number {
  const base = 5;
  return base + Math.min(6, (n.evidenceCount ?? 1) * 1.2);
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
  const ref = useRef<SVGSVGElement | null>(null);
  const [dims, setDims] = useState({ w: 640, h: 520 });
  const [, force] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);

  const { nodes, links } = useMemo(() => {
    const nmap = new Map<string, SimNode>();
    data.nodes.forEach((n, i) =>
      nmap.set(n.id, {
        ...n,
        x: dims.w / 2 + Math.cos(i) * 120,
        y: dims.h / 2 + Math.sin(i) * 120,
      }),
    );
    const lks: SimLink[] = [];
    data.edges.forEach((e) => {
      const s = nmap.get(e.source);
      const t = nmap.get(e.target);
      if (s && t) lks.push({ source: s, target: t, type: e.type, contradicted: e.contradicted });
    });
    return { nodes: [...nmap.values()], links: lks };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  useEffect(() => {
    const el = ref.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setDims({ w: r.width, h: Math.max(360, r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!nodes.length) return;
    const sim = forceSimulation<SimNode>(nodes)
      .force('charge', forceManyBody().strength(-180))
      .force('link', forceLink<SimNode, SimLink>(links).distance(70).strength(0.4))
      .force('center', forceCenter(dims.w / 2, dims.h / 2))
      .force('collide', forceCollide<SimNode>().radius((d) => radiusFor(d) + 6))
      .alpha(0.9)
      .on('tick', () => force((x) => x + 1));
    simRef.current = sim;
    return () => {
      sim.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, links, dims.w, dims.h]);

  const neighborIds = useMemo(() => {
    if (!hover) return null;
    const set = new Set<string>([hover]);
    links.forEach((l) => {
      if (l.source.id === hover) set.add(l.target.id);
      if (l.target.id === hover) set.add(l.source.id);
    });
    return set;
  }, [hover, links]);

  if (!nodes.length)
    return (
      <div className="flex h-full items-center justify-center text-faint font-mono text-sm">
        Граф появится после запроса
      </div>
    );

  return (
    <svg ref={ref} width="100%" height={dims.h} className="block">
      <defs>
        <radialGradient id="glow">
          <stop offset="0%" stopColor="#C87941" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#C87941" stopOpacity="0" />
        </radialGradient>
      </defs>
      <g>
        {links.map((l, i) => {
          const dim = neighborIds && !(neighborIds.has(l.source.id) && neighborIds.has(l.target.id));
          const stroke = l.contradicted ? '#E5484D' : '#C87941';
          return (
            <line
              key={i}
              x1={l.source.x}
              y1={l.source.y}
              x2={l.target.x}
              y2={l.target.y}
              stroke={stroke}
              strokeWidth={l.contradicted ? 1.6 : 0.9}
              strokeOpacity={dim ? 0.06 : 0.32}
              strokeDasharray={l.contradicted ? '4 3' : undefined}
              className={l.contradicted ? '' : 'animate-thread'}
            />
          );
        })}
        {nodes.map((n) => {
          const r = radiusFor(n);
          const dim = neighborIds && !neighborIds.has(n.id);
          const selected = selectedId === n.id;
          const isGap = n.type === 'Gap';
          return (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              opacity={dim ? 0.25 : 1}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(n)}
              style={{ cursor: 'pointer' }}
            >
              {selected && <circle r={r + 8} fill="url(#glow)" />}
              <circle
                r={r}
                fill={isGap ? 'transparent' : colorFor(n)}
                stroke={colorFor(n)}
                strokeWidth={isGap ? 1.6 : n.verified ? 2 : 0.5}
                strokeDasharray={isGap ? '3 2' : undefined}
                fillOpacity={n.verified ? 1 : 0.75}
              />
              {n.verified && <circle r={r + 2.5} fill="none" stroke="#3FB68B" strokeWidth={0.8} strokeOpacity={0.7} />}
              {(hover === n.id || selected) && (
                <text
                  x={r + 5}
                  y={4}
                  className="font-mono"
                  fontSize={11}
                  fill="#E9E6DF"
                  style={{ pointerEvents: 'none' }}
                >
                  {n.label.slice(0, 34)}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
