import { useEffect, useMemo, useState } from 'react';
import { Loader2, Quote, ScanText, FileImage, Hash, Type } from 'lucide-react';

// §5.7 / §8.3 — «Evidence из подписей рисунков». Every figure caption becomes a
// first-class :Evidence node with source_type=figure_caption, a real page and a real
// char_start/char_end span into the parsed page text, wired back to the :Figure it
// describes (caption→figure linkage). This view lets a curator pick an uploaded
// document, build the caption-evidence anchors, and inspect each one next to the crop
// of the figure it captions. Self-contained: it talks to /api/v1/figure-captions and
// /api/v1/documents directly, so it needs no api.ts wiring.

interface DocItem {
  doc_id: string;
  title: string | null;
  page_count?: number | null;
  year?: number | null;
}

interface CaptionEvidence {
  evidence_id: string;
  figure_id: string;
  doc_id: string;
  page: number;
  caption: string;
  char_start: number | null;
  char_end: number | null;
  bbox: number[];
  source_type: string;
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

export function FigureCaptionEvidenceView() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [docId, setDocId] = useState<string>('');
  const [items, setItems] = useState<CaptionEvidence[]>([]);
  const [selected, setSelected] = useState<CaptionEvidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    jget<{ documents: DocItem[] }>('/api/v1/documents?limit=100')
      .then((d) => {
        setDocs(d.documents);
        if (d.documents[0]) setDocId(d.documents[0].doc_id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const load = async (id: string) => {
    if (!id) return;
    setBusy(true);
    setError('');
    setSelected(null);
    try {
      const r = await jget<{ evidence: CaptionEvidence[] }>(
        `/api/v1/figure-captions/by-doc/${encodeURIComponent(id)}`,
      );
      setItems(r.evidence);
      setSelected(r.evidence[0] ?? null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load(docId);
  }, [docId]);

  const build = async () => {
    if (!docId) return;
    setBuilding(true);
    setError('');
    setNotice('');
    try {
      const r = await jpost<{
        captions_evidenced: number;
        figures_seen: number;
        self_extracted: boolean;
      }>(`/api/v1/figure-captions/build/${encodeURIComponent(docId)}`);
      setNotice(
        `Подписей-доказательств: ${r.captions_evidenced} из ${r.figures_seen} фигур` +
          (r.self_extracted ? ' · фигуры извлечены на лету' : ''),
      );
      await load(docId);
    } catch (e) {
      setError(String(e));
    } finally {
      setBuilding(false);
    }
  };

  const cropUrl = (e: CaptionEvidence) =>
    `/api/v1/figure-captions/${encodeURIComponent(e.figure_id)}/crop?dpi=200`;

  const currentDoc = useMemo(() => docs.find((d) => d.doc_id === docId), [docs, docId]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">доказательность</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Подписи рисунков как доказательства</h2>
        <p className="mb-5 max-w-3xl text-[13px] text-faint">
          Каждая подпись рисунка становится отдельным цитируемым доказательством: с номером
          страницы, точным местом в тексте и привязкой к своему рисунку. Так на подпись можно
          сослаться так же, как на любой другой источник.
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
                {d.page_count ? ` · ${d.page_count} стр.` : ''}
              </option>
            ))}
          </select>
          <button
            onClick={() => void build()}
            disabled={!docId || building}
            className="flex items-center gap-2 rounded-md bg-copper/15 px-3 py-2 text-sm text-copper transition hover:bg-copper/25 disabled:opacity-50"
          >
            {building ? <Loader2 size={15} className="animate-spin" /> : <ScanText size={15} />}
            Собрать доказательства из подписей
          </button>
        </div>

        {error && <div className="mb-4 text-sm text-contradiction">Ошибка: {error}</div>}
        {notice && <div className="mb-4 text-sm text-verified">{notice}</div>}

        {busy ? (
          <div className="flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={14} className="animate-spin text-copper" /> загрузка подписей…
          </div>
        ) : items.length === 0 ? (
          <div className="panel flex flex-col items-center gap-2 p-10 text-center">
            <FileImage size={28} className="text-faint" />
            <div className="text-sm text-nickel">
              Для этого документа доказательства из подписей ещё не собраны
            </div>
            <div className="text-[11px] text-faint">
              Нажмите «Собрать доказательства из подписей».
            </div>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
            {/* Caption rail */}
            <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1">
              {items.map((e) => (
                <button
                  key={e.evidence_id}
                  onClick={() => setSelected(e)}
                  className={`flex gap-3 rounded-md border p-2 text-left transition ${
                    selected?.evidence_id === e.evidence_id
                      ? 'border-copper bg-copper/10'
                      : 'border-line hover:border-copper/40'
                  }`}
                >
                  <img
                    src={cropUrl(e)}
                    alt={`figure p${e.page}`}
                    loading="lazy"
                    className="h-16 w-16 shrink-0 rounded bg-graphite/40 object-contain"
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 text-[11px] text-faint">
                      <Quote size={11} /> стр. {e.page}
                    </div>
                    <div className="line-clamp-2 text-[12px] text-nickel">
                      {e.caption || 'Без подписи'}
                    </div>
                  </div>
                </button>
              ))}
            </div>

            {/* Detail viewer */}
            <div className="panel p-4">
              {selected ? (
                <>
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-[10px] text-faint">
                    <span className="chip">стр. {selected.page}</span>
                    <span className="chip flex items-center gap-1">
                      <Type size={10} /> {selected.source_type}
                    </span>
                    {selected.char_start != null && selected.char_end != null && (
                      <span className="chip flex items-center gap-1 font-mono">
                        <Hash size={10} /> {selected.char_start}–{selected.char_end}
                      </span>
                    )}
                  </div>
                  <img
                    src={cropUrl(selected)}
                    alt={`figure crop p${selected.page}`}
                    className="mb-3 max-h-[46vh] w-full rounded-md bg-graphite/30 object-contain"
                  />
                  <blockquote className="border-l-2 border-copper/60 pl-3 text-[13px] leading-relaxed text-ink">
                    {selected.caption || 'Без подписи'}
                  </blockquote>
                  <div className="mt-3 flex flex-wrap gap-4 font-mono text-[10px] text-faint">
                    <span>evidence: {selected.evidence_id}</span>
                    <span>figure: {selected.figure_id}</span>
                  </div>
                </>
              ) : (
                <div className="flex h-40 items-center justify-center text-sm text-faint">
                  Выберите подпись слева
                </div>
              )}
            </div>
          </div>
        )}

        {currentDoc && (
          <div className="mt-4 text-[11px] text-faint">
            Источник: {currentDoc.title || currentDoc.doc_id}
            {currentDoc.year ? ` · ${currentDoc.year}` : ''}
          </div>
        )}
      </div>
    </div>
  );
}
