import { lazy, Suspense, useState } from 'react';
import { Box, Loader2, Square } from 'lucide-react';
import type { GraphNode, GraphResponse } from '../types';
import { GraphView } from './GraphView';

// Graph Explorer shell (§17.18): a 2D canvas by default with a one-click «3D» wow-mode.
// The three.js / react-force-graph bundle is heavy, so the 3D renderer is lazy-loaded
// — it ships to the browser only when the user actually flips to 3D.
const ForceGraph3DView = lazy(() => import('./ForceGraph3DView'));

export function GraphPanel({
  data,
  onSelect,
  selectedId,
}: {
  data: GraphResponse;
  onSelect?: (n: GraphNode) => void;
  selectedId?: string | null;
}) {
  const [is3d, setIs3d] = useState(false);

  return (
    <div className="relative h-full w-full">
      {/* 2D / 3D switch — top-left, above the canvas */}
      <div className="absolute left-2 top-2 z-10 flex overflow-hidden rounded-md border border-line bg-graphite/80 backdrop-blur">
        <button
          onClick={() => setIs3d(false)}
          className={`flex items-center gap-1 px-2.5 py-1 text-[11px] transition ${
            is3d ? 'text-faint hover:text-nickel' : 'bg-copper/20 text-copper'
          }`}
          title="Плоский граф"
        >
          <Square size={12} /> 2D
        </button>
        <button
          onClick={() => setIs3d(true)}
          className={`flex items-center gap-1 px-2.5 py-1 text-[11px] transition ${
            is3d ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
          }`}
          title="Объёмный клубок — вращайте мышью"
        >
          <Box size={12} /> 3D
        </button>
      </div>

      {is3d ? (
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center gap-2 bg-graphite font-mono text-xs text-faint">
              <Loader2 size={14} className="animate-spin text-copper" /> загрузка 3D-движка…
            </div>
          }
        >
          <ForceGraph3DView data={data} onSelect={onSelect} />
        </Suspense>
      ) : (
        <GraphView data={data} onSelect={onSelect} selectedId={selectedId} />
      )}
    </div>
  );
}
