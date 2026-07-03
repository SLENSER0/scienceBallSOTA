import { useQuery } from '@tanstack/react-query';
import { FileText, Loader2, X } from 'lucide-react';
import { api } from '../api';
import { useStore } from '../store';
import type { EvidenceContext } from '../types';

// Node inspector + Evidence Inspector (§17.13). For a plain node it shows its
// properties; for an Evidence node it fetches the source chunk and renders the cited
// span HIGHLIGHTED in the actual paragraph it came from, with full provenance
// (source, geography, vintage, strength) — so a citation is verifiable in one click.

const PRACTICE: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};

export function EvidenceDrawer() {
  const { selectedNode, setSelectedNode } = useStore();
  const isEvidence = selectedNode?.type === 'Evidence';
  const ctx = useQuery({
    queryKey: ['evidence-context', selectedNode?.id],
    queryFn: () => api.evidenceContext(selectedNode!.id),
    enabled: !!selectedNode && isEvidence,
  });

  if (!selectedNode) return null;
  const props = (selectedNode.properties ?? {}) as Record<string, unknown>;

  return (
    <aside className="animate-rise fixed right-0 top-0 z-20 flex h-full w-96 flex-col border-l border-line bg-graphite/95 shadow-panel backdrop-blur">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="eyebrow">
          {isEvidence ? 'инспектор доказательства' : `инспектор · ${selectedNode.type}`}
        </div>
        <button onClick={() => setSelectedNode(null)} className="text-faint hover:text-ink">
          <X size={16} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {isEvidence ? (
          ctx.isLoading ? (
            <div className="flex items-center gap-2 font-mono text-xs text-faint">
              <Loader2 size={14} className="animate-spin text-copper" /> загрузка контекста…
            </div>
          ) : ctx.data ? (
            <EvidenceInspector c={ctx.data} />
          ) : (
            <div className="text-sm text-faint">Контекст недоступен.</div>
          )
        ) : (
          <>
            <h3 className="mb-3 font-display text-base leading-snug text-ink">
              {selectedNode.label}
            </h3>
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
                    <dd className="text-right font-mono text-xs text-ink/90">
                      {String(v).slice(0, 60)}
                    </dd>
                  </div>
                ))}
            </dl>
            <div className="mt-4 font-mono text-[11px] text-faint">id: {selectedNode.id}</div>
          </>
        )}
      </div>
    </aside>
  );
}

function EvidenceInspector({ c }: { c: EvidenceContext }) {
  return (
    <div>
      {/* Source header */}
      <div className="mb-3 flex items-start gap-2">
        <FileText size={16} className="mt-0.5 shrink-0 text-copper" />
        <div className="min-w-0">
          <div className="truncate text-sm text-ink">{c.doc_title || c.doc_id || 'источник'}</div>
          <div className="mt-0.5 flex flex-wrap gap-1.5">
            {c.practice_type && (
              <span className="chip text-faint">{PRACTICE[c.practice_type] ?? c.practice_type}</span>
            )}
            {c.year && <span className="chip text-faint">{c.year}</span>}
            {c.page != null && <span className="chip text-faint">стр. {c.page}</span>}
            {c.evidence_strength && <span className="chip text-faint">{c.evidence_strength}</span>}
            {typeof c.confidence === 'number' && (
              <span className="chip text-copper">conf {Math.round(c.confidence * 100)}%</span>
            )}
          </div>
        </div>
      </div>

      {/* Chunk with highlighted span */}
      <div className="eyebrow mb-1.5">цитата в контексте абзаца</div>
      <div className="rounded-md border border-line bg-surface/50 px-3 py-2.5 text-[13px] leading-relaxed text-ink/90">
        <HighlightedChunk c={c} />
      </div>
    </div>
  );
}

function HighlightedChunk({ c }: { c: EvidenceContext }) {
  const { chunk_text, highlight_offset: off, highlight_len: len } = c;
  // No reliable offset → just show the span itself as the highlight.
  if (off < 0 || len <= 0) {
    return <mark className="rounded bg-copper/25 px-0.5 text-ink">{c.span}</mark>;
  }
  const start = Math.max(0, off - 400);
  const end = off + len + 400;
  const before = (start > 0 ? '…' : '') + chunk_text.slice(start, off);
  const hit = chunk_text.slice(off, off + len);
  const after = chunk_text.slice(off + len, end) + (chunk_text.length > end ? '…' : '');
  return (
    <>
      {before}
      <mark className="rounded bg-copper/30 px-0.5 font-medium text-ink">{hit}</mark>
      {after}
    </>
  );
}
