import { useEffect, useMemo, useState } from 'react';
import { Image as ImageIcon, Loader2, ScanSearch, Crop, FileImage, Link2 } from 'lucide-react';

// §23.34 — «Фигуры как evidence». Figures (charts / micrographs / flowsheets) are
// pulled out of the source PDF into the graph as :Figure nodes with a page + bbox,
// and each is wired (SUPPORTED_BY) to the facts whose evidence lives on that page.
// This view lets a user pick an uploaded document, run extraction, then inspect each
// figure either as a tight crop or highlighted in place on the real PDF page — the
// "here is the picture that proves it" evidence view. Fully self-contained: it talks
// to /api/v1/figures and /api/v1/documents directly, so it needs no api.ts wiring.

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

interface Figure {
  figure_id: string;
  doc_id: string;
  page: number;
  bbox: number[];
  caption: string;
  supported_facts: number;
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

async function jget<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function jpost<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: 'POST', headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => res.statusText)}`);
  return res.json() as Promise<T>;
}

export function FigureEvidenceView() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [docId, setDocId] = useState<string>('');
  const [figs, setFigs] = useState<Figure[]>([]);
  const [selected, setSelected] = useState<Figure | null>(null);
  const [mode, setMode] = useState<'crop' | 'highlight'>('highlight');
  const [busy, setBusy] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    // Corpus-wide listing (backend already sorts has_parsed-first, so parsed docs
    // — the ones that actually have rasterized pages/figures — surface at the top).
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

  const loadFigs = async (id: string) => {
    if (!id) return;
    setBusy(true);
    setError('');
    setSelected(null);
    try {
      const r = await jget<{ figures: Figure[] }>(`/api/v1/figures/by-doc/${encodeURIComponent(id)}`);
      setFigs(r.figures ?? []);
      setSelected(r.figures?.[0] ?? null);
    } catch {
      // Corpus :Paper nodes have no rasterized pages, so by-doc may 4xx/error or
      // return nothing. Degrade to the empty state instead of a scary error banner.
      setFigs([]);
      setSelected(null);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadFigs(docId);
  }, [docId]);

  const extract = async () => {
    if (!docId) return;
    setExtracting(true);
    setError('');
    setNotice('');
    try {
      const r = await jpost<{ count: number; linked_facts: number }>(
        `/api/v1/figures/extract/${encodeURIComponent(docId)}`,
      );
      setNotice(`Извлечено фигур: ${r.count} · связано с фактами: ${r.linked_facts}`);
      await loadFigs(docId);
    } catch (e) {
      // A corpus :Paper without an uploaded PDF returns 404/415 — show a neutral hint
      // rather than dumping the raw error JSON into a red banner.
      const msg = String(e);
      if (msg.includes('404') || msg.includes('415')) {
        setNotice('Для этого источника нет загруженного PDF — извлечение фигур недоступно.');
      } else {
        setError(msg);
      }
    } finally {
      setExtracting(false);
    }
  };

  const imgUrl = (f: Figure, m: 'crop' | 'highlight') =>
    `/api/v1/figures/${encodeURIComponent(f.figure_id)}/image?mode=${m}&dpi=${m === 'highlight' ? 130 : 200}`;

  const currentDoc = useMemo(() => docs.find((d) => d.doc_id === docId), [docs, docId]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">доказательность</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Фигуры как доказательства</h2>
        <p className="mb-5 max-w-3xl text-[13px] text-faint">
          Графики, микроструктуры и схемы из статей — рядом с фактами, которые они
          подтверждают. Кликните по фигуре: увидите её отдельным вырезом или
          подсвеченной прямо на странице статьи.
        </p>

        {/* Controls */}
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
          <button
            onClick={() => void extract()}
            disabled={!docId || extracting || (currentDoc != null && !currentDoc.has_parsed)}
            title={
              currentDoc && !currentDoc.has_parsed
                ? 'Нет загруженного PDF для этого источника — извлечение фигур недоступно'
                : 'Извлечь фигуры из PDF-источника'
            }
            className="flex items-center gap-2 rounded-md bg-copper/15 px-3 py-2 text-sm text-copper transition hover:bg-copper/25 disabled:opacity-50"
          >
            {extracting ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />}
            Извлечь фигуры
          </button>
        </div>

        {error && <div className="mb-4 text-sm text-contradiction">Ошибка: {error}</div>}
        {notice && <div className="mb-4 text-sm text-verified">{notice}</div>}

        {busy ? (
          <div className="flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={14} className="animate-spin text-copper" /> загрузка фигур…
          </div>
        ) : figs.length === 0 ? (
          <div className="panel flex flex-col items-center gap-2 p-10 text-center">
            <FileImage size={28} className="text-faint" />
            <div className="text-sm text-nickel">
              Для этого документа фигуры ещё не извлечены
            </div>
            <div className="mx-auto max-w-md text-[11px] leading-relaxed text-faint">
              Постраничные фигуры доступны для документов с распознанными страницами
              (например, загруженных PDF): нажмите «Извлечь фигуры» для такого источника.
              Полный список источников корпуса можно просмотреть в разделе
              «Библиотека → Источники корпуса».
            </div>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
            {/* Thumbnail rail */}
            <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1">
              {figs.map((f) => (
                <button
                  key={f.figure_id}
                  onClick={() => setSelected(f)}
                  className={`flex gap-3 rounded-md border p-2 text-left transition ${
                    selected?.figure_id === f.figure_id
                      ? 'border-copper bg-copper/10'
                      : 'border-line hover:border-copper/40'
                  }`}
                >
                  <img
                    src={imgUrl(f, 'crop')}
                    alt={`figure p${f.page}`}
                    loading="lazy"
                    className="h-16 w-16 shrink-0 rounded bg-graphite/40 object-contain"
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 text-[11px] text-faint">
                      <ImageIcon size={11} /> стр. {f.page}
                    </div>
                    <div className="truncate text-[12px] text-nickel">
                      {f.caption || 'Без подписи'}
                    </div>
                    {f.supported_facts > 0 && (
                      <div className="mt-0.5 flex items-center gap-1 text-[10px] text-copper">
                        <Link2 size={10} /> {f.supported_facts} факт(ов)
                      </div>
                    )}
                  </div>
                </button>
              ))}
            </div>

            {/* Detail viewer */}
            <div className="panel p-4">
              {selected ? (
                <>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-ink">
                        {selected.caption || `Фигура на стр. ${selected.page}`}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-faint">
                        <span className="chip">стр. {selected.page}</span>
                        <span className="font-mono">
                          bbox [{selected.bbox.map((v) => Math.round(v)).join(', ')}]
                        </span>
                        {selected.supported_facts > 0 && (
                          <span className="chip text-copper">
                            {selected.supported_facts} факт(ов)
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex overflow-hidden rounded-md border border-line">
                      <button
                        onClick={() => setMode('highlight')}
                        className={`flex items-center gap-1 px-2.5 py-1.5 text-xs transition ${
                          mode === 'highlight' ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
                        }`}
                      >
                        <ScanSearch size={13} /> На странице
                      </button>
                      <button
                        onClick={() => setMode('crop')}
                        className={`flex items-center gap-1 px-2.5 py-1.5 text-xs transition ${
                          mode === 'crop' ? 'bg-copper/20 text-copper' : 'text-faint hover:text-nickel'
                        }`}
                      >
                        <Crop size={13} /> Кроп
                      </button>
                    </div>
                  </div>
                  <div className="flex justify-center rounded-md bg-graphite/40 p-3">
                    <img
                      key={selected.figure_id + mode}
                      src={imgUrl(selected, mode)}
                      alt="figure evidence"
                      className="max-h-[62vh] max-w-full rounded object-contain"
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-faint">
                    {currentDoc?.title ? `${currentDoc.title} · ` : ''}
                    {mode === 'highlight'
                      ? 'Оранжевой рамкой выделена фигура на исходной странице статьи.'
                      : 'Точный вырез фигуры из статьи.'}
                  </p>
                </>
              ) : (
                <div className="flex h-40 items-center justify-center font-mono text-xs text-faint">
                  выберите фигуру слева
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
