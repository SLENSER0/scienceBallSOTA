import { X } from 'lucide-react';
import { useStore } from '../store';

export function EvidenceDrawer() {
  const { selectedNode, setSelectedNode } = useStore();
  if (!selectedNode) return null;
  const props = (selectedNode.properties ?? {}) as Record<string, unknown>;

  return (
    <aside className="animate-rise fixed right-0 top-0 z-20 flex h-full w-80 flex-col border-l border-line bg-graphite/95 shadow-panel backdrop-blur">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="eyebrow">инспектор · {selectedNode.type}</div>
        <button onClick={() => setSelectedNode(null)} className="text-faint hover:text-ink">
          <X size={16} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <h3 className="mb-3 font-display text-base leading-snug text-ink">{selectedNode.label}</h3>
        {typeof props.text === 'string' && (
          <blockquote className="mb-4 rounded border-l-2 border-copper bg-surface/60 px-3 py-2 text-sm italic text-ink/85">
            «{props.text as string}»
          </blockquote>
        )}
        <dl className="space-y-2 text-sm">
          {Object.entries(props)
            .filter(([k, v]) => v != null && v !== '' && k !== 'text' && k !== 'props')
            .slice(0, 24)
            .map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-line/50 pb-1.5">
                <dt className="font-mono text-[11px] uppercase tracking-wide text-faint">{k}</dt>
                <dd className="text-right font-mono text-xs text-ink/90">{String(v).slice(0, 60)}</dd>
              </div>
            ))}
        </dl>
        <div className="mt-4 font-mono text-[11px] text-faint">id: {selectedNode.id}</div>
      </div>
    </aside>
  );
}
