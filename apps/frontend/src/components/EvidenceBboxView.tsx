import { useEffect, useMemo, useState } from 'react';
import { Loader2, ScanSearch, Crop, FileText, MapPin, Quote } from 'lucide-react';

// §14.9 — «Bbox-подсветка evidence на изображении страницы». Text evidence carries a
// locator (doc_id + page + cited text) but no pixel geometry, so the inspector could
// only say «страница 7». This view closes the last mile of evidence-first: pick a
// document, pick a cited span, and the exact rectangle the citation came from is
// located on the source PDF (PyMuPDF full-text search) and highlighted in place —
// «клик по цитате → прыжок к точному прямоугольнику на скане». Fully self-contained:
// it talks to /api/v1/evidence-bbox and /api/v1/documents directly, no api.ts wiring.

interface DocItem {
  doc_id: string;
  title: string | null;
  page_count?: number | null;
  year?: number | null;
  has_parsed?: boolean;
}

// Corpus-wide source listing (graph :Paper / :Document nodes), not just uploaded
// sidecars. has_parsed=true means a parsed page-image sidecar exists for this doc.
interface CorpusSource {
  doc_id: string;
  title: string | null;
  has_parsed?: boolean;
}

interface EvidenceItem {
  evidence_id: string;
  page: number;
  text: string;
  confidence?: number | null;
  evidence_strength?: string | null;
  source_type?: string | null;
}

interface LocateResult {
  evidence_id: string;
  doc_id: string;
  page: number;
  page_width: number;
  page_height: number;
  bbox: number[] | null;
  line_rects: number[][];
  match_quality: 'exact' | 'phrase' | 'word' | 'none';
  found: boolean;
  span: string;
}

const QUALITY_LABEL: Record<LocateResult['match_quality'], string> = {
  exact: 'точное совпадение',
  phrase: 'по фразам',
  word: 'по слову',
  none: 'не найдено на странице',
};

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

async function jget<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function EvidenceBboxView() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [docId, setDocId] = useState<string>('');
  const [items, setItems] = useState<EvidenceItem[]>([]);
  const [selected, setSelected] = useState<EvidenceItem | null>(null);
  const [locate, setLocate] = useState<LocateResult | null>(null);
  const [mode, setMode] = useState<'page' | 'crop'>('page');
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Corpus-wide listing (backend already sorts has_parsed-first, so parsed docs
    // — the ones that actually have page images/citations — surface at the top).
    jget<{ sources: CorpusSource[] }>('/api/v1/documents/corpus?limit=200')
      .then((d) => {
        const mapped: DocItem[] = (d.sources ?? []).map((s) => ({
          doc_id: s.doc_id,
          title: s.title,
          has_parsed: s.has_parsed,
        }));
        setDocs(mapped);
        if (mapped[0]) setDocId(mapped[0].doc_id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!docId) return;
    setBusy(true);
    setError('');
    setSelected(null);
    setLocate(null);
    jget<{ evidence: EvidenceItem[] }>(`/api/v1/evidence-bbox/by-doc/${encodeURIComponent(docId)}`)
      .then((r) => {
        setItems(r.evidence ?? []);
        setSelected(r.evidence?.[0] ?? null);
      })
      .catch(() => {
        // Corpus :Paper nodes have no rasterized pages, so by-doc may 4xx/error or
        // return nothing. Degrade to the empty state instead of a scary error banner.
        setItems([]);
        setSelected(null);
      })
      .finally(() => setBusy(false));
  }, [docId]);

  useEffect(() => {
    if (!selected) {
      setLocate(null);
      return;
    }
    setLocating(true);
    setLocate(null);
    jget<LocateResult>(`/api/v1/evidence-bbox/locate/${encodeURIComponent(selected.evidence_id)}`)
      .then(setLocate)
      // A doc without page images can't be located — fall back to no-locate quietly
      // rather than surfacing an error for something the user can't act on.
      .catch(() => setLocate(null))
      .finally(() => setLocating(false));
  }, [selected]);

  const imgUrl = useMemo(() => {
    if (!selected) return '';
    const pad = mode === 'crop' ? 24 : -1;
    const dpi = mode === 'crop' ? 200 : 130;
    return `/api/v1/evidence-bbox/${encodeURIComponent(selected.evidence_id)}/image?mode=${mode}&dpi=${dpi}&pad=${pad}`;
  }, [selected, mode]);

  const currentDoc = useMemo(() => docs.find((d) => d.doc_id === docId), [docs, docId]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">доказательность</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Цитата, подсвеченная на странице</h2>
        <p className="mb-5 max-w-3xl text-[13px] text-faint">
          У каждой цитаты известны документ, страница и точный текст. Здесь цитата находится
          на исходной странице статьи и подсвечивается прямо на ней — «клик по цитате →
          переход к нужному месту».
        </p>

        <div className="panel mb-5 flex flex-wrap items-center gap-3 p-3">
          <label className="text-xs text-nickel">Документ</label>
          <select
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            className="min-w-[280px] flex-1 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
          >
            {docs.length === 0 && <option value="">— нет загруженных документов —</option>}
            {docs.map((d) => (
              <option key={d.doc_id} value={d.doc_id}>
                {(d.title || d.doc_id).slice(0, 80)}
                {d.has_parsed ? ' · PDF' : ''}
              </option>
            ))}
          </select>
        </div>

        {error && <div className="mb-4 text-sm text-contradiction">Ошибка: {error}</div>}

        {busy ? (
          <div className="flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={14} className="animate-spin text-copper" /> загрузка цитат…
          </div>
        ) : items.length === 0 ? (
          <div className="panel flex flex-col items-center gap-2 p-10 text-center">
            <FileText size={28} className="text-faint" />
            <div className="text-sm text-nickel">
              У этого документа нет текстовых доказательств со страницей
            </div>
            <div className="mx-auto max-w-md text-[11px] leading-relaxed text-faint">
              Подсветка цитат на странице доступна для документов с распознанными
              страницами (например, загруженных PDF): загрузите PDF и запустите
              извлечение — цитаты с page+text появятся здесь. Полный список источников
              корпуса можно просмотреть в разделе «Библиотека → Источники корпуса».
            </div>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
            {/* Citation rail */}
            <div className="flex max-h-[72vh] flex-col gap-2 overflow-y-auto pr-1">
              {items.map((e) => (
                <button
                  key={e.evidence_id}
                  onClick={() => setSelected(e)}
                  className={`rounded-md border p-2 text-left transition ${
                    selected?.evidence_id === e.evidence_id
                      ? 'border-copper bg-copper/10'
                      : 'border-line hover:border-copper/40'
                  }`}
                >
                  <div className="mb-1 flex items-center gap-1.5 text-[11px] text-faint">
                    <Quote size={11} /> стр. {e.page}
                    {e.evidence_strength && <span className="chip">{e.evidence_strength}</span>}
                    {typeof e.confidence === 'number' && (
                      <span className="font-mono">{e.confidence.toFixed(2)}</span>
                    )}
                  </div>
                  <div className="line-clamp-3 text-[12px] leading-snug text-nickel">
                    {e.text}
                  </div>
                </button>
              ))}
            </div>

            {/* Page viewer */}
            <div className="panel p-4">
              {selected ? (
                <>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="line-clamp-2 text-sm text-ink">«{selected.text}»</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-faint">
                        <span className="chip">стр. {selected.page}</span>
                        {locating ? (
                          <span className="flex items-center gap-1">
                            <Loader2 size={10} className="animate-spin" /> поиск на странице…
                          </span>
                        ) : locate ? (
                          <>
                            <span
                              className={`chip ${locate.found ? 'text-copper' : 'text-contradiction'}`}
                            >
                              <MapPin size={10} className="mr-0.5 inline" />
                              {QUALITY_LABEL[locate.match_quality]}
                            </span>
                            {locate.bbox && (
                              <span className="font-mono">
                                bbox [{locate.bbox.map((v) => Math.round(v)).join(', ')}]
                              </span>
                            )}
                          </>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex overflow-hidden rounded-md border border-line">
                      <button
                        onClick={() => setMode('page')}
                        className={`flex items-center gap-1 px-2.5 py-1.5 text-xs transition ${
                          mode === 'page' ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
                        }`}
                      >
                        <ScanSearch size={13} /> На странице
                      </button>
                      <button
                        onClick={() => setMode('crop')}
                        disabled={!locate?.found}
                        className={`flex items-center gap-1 px-2.5 py-1.5 text-xs transition disabled:opacity-40 ${
                          mode === 'crop' ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
                        }`}
                      >
                        <Crop size={13} /> Кроп
                      </button>
                    </div>
                  </div>
                  <div className="flex justify-center rounded-md bg-graphite/40 p-3">
                    {locating ? (
                      <div className="flex h-40 items-center gap-2 font-mono text-xs text-faint">
                        <Loader2 size={14} className="animate-spin text-copper" /> рендер страницы…
                      </div>
                    ) : (
                      <img
                        key={imgUrl}
                        src={imgUrl}
                        alt="evidence page"
                        className="max-h-[64vh] max-w-full rounded object-contain"
                      />
                    )}
                  </div>
                  <p className="mt-2 text-[11px] text-faint">
                    {currentDoc?.title ? `${currentDoc.title} · ` : ''}
                    {locate?.found
                      ? mode === 'page'
                        ? 'Медной рамкой выделен точный прямоугольник цитаты на исходной странице.'
                        : 'Тесный вырез вокруг найденной цитаты.'
                      : 'Цитата не локализована на странице — показан общий вид страницы.'}
                  </p>
                </>
              ) : (
                <div className="flex h-40 items-center justify-center font-mono text-xs text-faint">
                  выберите цитату слева
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
