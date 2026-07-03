import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import type { GraphNode, GraphResponse } from '../types';

// «Клубок 3D» — wow-mode Graph Explorer (§17.18) on react-force-graph (three.js).
// Same GraphResponse + §5.2.3 visual encodings as the 2D canvas view; rotate/zoom/pan,
// click a node → detail. Lazy-loaded (heavy three.js bundle) only when 3D is chosen.

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
const MAX_NODES = 600;

interface Link3 {
  source: string;
  target: string;
  contradicted?: boolean | null;
}

export function ForceGraph3DView({
  data,
  onSelect,
}: {
  data: GraphResponse;
  onSelect?: (n: GraphNode) => void;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [dims, setDims] = useState({ w: 640, h: 480 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((es) => {
      const r = es[0].contentRect;
      setDims({ w: r.width, h: Math.max(320, r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const graph = useMemo(() => {
    const deg = new Map<string, number>();
    for (const e of data.edges) {
      deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
      deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    }
    let nodes = data.nodes.map((n) => ({ ...n, deg: deg.get(n.id) ?? 0 }));
    if (nodes.length > MAX_NODES) {
      nodes = [...nodes].sort((a, b) => b.deg - a.deg).slice(0, MAX_NODES);
    }
    const keep = new Set(nodes.map((n) => n.id));
    const links: Link3[] = data.edges
      .filter((e) => keep.has(e.source) && keep.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, contradicted: e.contradicted }));
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        name: n.label,
        type: n.type,
        val: 1 + Math.min(8, (n.evidenceCount ?? 1) + (n.deg ?? 0) * 0.3),
        color: TYPE_COLOR[n.type] ?? '#8FA3B0',
        raw: n,
      })),
      links,
    };
  }, [data]);

  return (
    <div ref={wrapRef} className="h-full w-full bg-graphite">
      <ForceGraph3D
        graphData={graph}
        width={dims.w}
        height={dims.h}
        backgroundColor="#14161a"
        nodeColor={(n: any) => n.color}
        nodeVal={(n: any) => n.val}
        nodeLabel={(n: any) => `${n.name} · ${n.type}`}
        nodeOpacity={0.9}
        linkColor={(l: any) => (l.contradicted ? '#E5484D' : '#C87941')}
        linkOpacity={0.28}
        linkWidth={(l: any) => (l.contradicted ? 1.2 : 0.5)}
        linkDirectionalParticles={0}
        onNodeClick={(n: any) => onSelect?.(n.raw)}
        enableNodeDrag={false}
        showNavInfo={false}
      />
    </div>
  );
}

export default ForceGraph3DView;
