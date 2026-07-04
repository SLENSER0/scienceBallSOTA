import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  History,
  Loader2,
  Pencil,
  RotateCcw,
  Save,
  Table2,
  Wrench,
} from 'lucide-react';
import { useStore } from '../store';

// §5.8 — Fallback-парсеры + ручная правка таблицы как новая версия артефакта.
// Standalone view: показывает статус цепочки docling→marker→unstructured→default,
// даёт куратору выбрать документ и таблицу, отредактировать сетку и сохранить как
// НОВУЮ версию (corrected=true, parser_used=manual) — исходник парсера сохраняется.

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

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

interface ParserReadiness {
  available: boolean;
  kind: string;
  formats: string[];
}
interface FallbackStatus {
  parsers: Record<string, ParserReadiness>;
  priority: { order: Record<string, string[]>; default: string[] };
  primary: string;
  primaryAvailable: boolean;
}
interface DocItem {
  doc_id: string;
  title?: string;
  doc_type?: string;
  page_count?: number;
}
interface TableSummary {
  tableIndex: number;
  page: number | null;
  nRows: number;
  nCols: number;
  corrected: boolean;
  versionCount: number;
  currentVersion: number;
  parserUsed: string;
}
interface TableVersion {
  version: number;
  rows: string[][];
  page: number | null;
  parserUsed: string;
  corrected: boolean;
  reason: string;
  author: string;
  createdAt: number;
  baseParser: string;
}
interface Lineage {
  docId: string;
  tableIndex: number;
  versionCount: number;
  corrected: boolean;
  current: TableVersion;
  versions: TableVersion[];
}

const PARSER_ORDER = ['docling', 'marker', 'unstructured', 'default'];

export function TableCorrectionView() {
  const { role } = useStore();
  const canCorrect = ['admin', 'curator', 'researcher', 'analyst', 'project_manager'].includes(role);

  const [status, setStatus] = useState<FallbackStatus | null>(null);
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [docId, setDocId] = useState('');
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [tableIndex, setTableIndex] = useState<number | null>(null);
  const [lineage, setLineage] = useState<Lineage | null>(null);
  const [draft, setDraft] = useState<string[][]>([]);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Initial load: fallback status + document list.
  useEffect(() => {
    void (async () => {
      try {
        setStatus(await get<FallbackStatus>('/api/v1/parsers/fallback-status'));
      } catch {
        /* status is best-effort */
      }
      try {
        const d = await get<{ documents: DocItem[] }>('/api/v1/documents?limit=50');
        setDocs(d.documents ?? []);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  const loadTables = async (id: string) => {
    setDocId(id);
    setTables([]);
    setTableIndex(null);
    setLineage(null);
    setError(null);
    if (!id) return;
    setBusy(true);
    try {
      const r = await get<{ tables: TableSummary[] }>(
        `/api/v1/parsed-tables/${encodeURIComponent(id)}`,
      );
      setTables(r.tables ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const loadLineage = async (idx: number) => {
    setTableIndex(idx);
    setError(null);
    setToast(null);
    setBusy(true);
    try {
      const r = await get<Lineage>(
        `/api/v1/parsed-tables/${encodeURIComponent(docId)}/${idx}/versions`,
      );
      setLineage(r);
      setDraft(r.current.rows.map((row) => [...row]));
      setReason('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const original = useMemo(
    () => lineage?.versions.find((v) => v.version === 0) ?? null,
    [lineage],
  );

  const dirty = useMemo(() => {
    if (!lineage) return false;
    return JSON.stringify(draft) !== JSON.stringify(lineage.current.rows);
  }, [draft, lineage]);

  const editCell = (r: number, c: number, value: string) => {
    setDraft((prev) => {
      const next = prev.map((row) => [...row]);
      next[r][c] = value;
      return next;
    });
  };

  const addRow = () => {
    setDraft((prev) => {
      const width = prev[0]?.length ?? 1;
      return [...prev, Array.from({ length: width }, () => '')];
    });
  };

  const resetDraft = () => {
    if (lineage) setDraft(lineage.current.rows.map((row) => [...row]));
  };

  const submit = async () => {
    if (tableIndex === null || !dirty) return;
    setSaving(true);
    setError(null);
    setToast(null);
    try {
      const res = await fetch(
        `/api/v1/parsed-tables/${encodeURIComponent(docId)}/${tableIndex}/correct`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ rows: draft, reason }),
        },
      );
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = (await res.json()) as { created: TableVersion; lineage: Lineage };
      setLineage(data.lineage);
      setDraft(data.created.rows.map((row) => [...row]));
      setReason('');
      setToast(`Сохранена версия v${data.created.version} (corrected=true, parser_used=manual)`);
      // Refresh the table list so the «исправлено» badge updates.
      void loadTablesSilent(docId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const loadTablesSilent = async (id: string) => {
    try {
      const r = await get<{ tables: TableSummary[] }>(
        `/api/v1/parsed-tables/${encodeURIComponent(id)}`,
      );
      setTables(r.tables ?? []);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <div className="mb-1 flex items-center gap-2">
        <Wrench size={18} className="text-copper" />
        <h1 className="text-lg font-semibold text-ink">
          Fallback-парсеры и ручная правка таблиц
        </h1>
      </div>
      <p className="mb-5 text-sm text-muted">
        Устойчивость к трудным PDF: цепочка docling → marker → unstructured → встроенный парсер. Если
        docling недоступен, документ всё равно разбирается fallback-парсером. Куратор может исправить
        распознанную таблицу — правка сохраняется как <b>новая версия</b> артефакта (corrected=true,
        parser_used=manual), не затирая исходный вывод парсера.
      </p>

      {/* Fallback chain status */}
      {status && (
        <div className="mb-6 rounded-md border border-line bg-surface/40 p-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="eyebrow">цепочка fallback</span>
            <span
              className={`chip ${status.primaryAvailable ? 'text-verified' : 'text-gap'}`}
              title="Доступность основного парсера (docling)"
            >
              {status.primaryAvailable ? 'docling онлайн' : 'docling офлайн → fallback'}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {PARSER_ORDER.map((name, i) => {
              const p = status.parsers[name];
              const ok = p?.available;
              return (
                <span key={name} className="flex items-center gap-2">
                  <span
                    className={`chip flex items-center gap-1.5 ${ok ? 'text-verified' : 'text-faint'}`}
                    title={p ? `${p.kind} · ${p.formats.join(', ')}` : 'нет данных'}
                  >
                    {ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                    {name}
                  </span>
                  {i < PARSER_ORDER.length - 1 && <span className="text-faint">→</span>}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Document + table selectors */}
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="flex flex-col text-xs text-muted">
          Документ
          <select
            value={docId}
            onChange={(e) => void loadTables(e.target.value)}
            className="mt-1 min-w-[16rem] rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
          >
            <option value="">— выберите документ —</option>
            {docs.map((d) => (
              <option key={d.doc_id} value={d.doc_id}>
                {d.title || d.doc_id}
              </option>
            ))}
          </select>
        </label>
      </div>

      {busy && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Loader2 size={14} className="animate-spin" /> Загрузка…
        </div>
      )}

      {error && (
        <div className="mt-2 rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
          Ошибка: {error}
        </div>
      )}

      {/* Table chips */}
      {docId && tables.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {tables.map((t) => (
            <button
              key={t.tableIndex}
              onClick={() => void loadLineage(t.tableIndex)}
              className={`chip flex items-center gap-1.5 ${
                tableIndex === t.tableIndex ? 'border-copper/60 text-copper' : 'text-nickel'
              }`}
              title={`стр. ${t.page ?? '—'} · ${t.nRows}×${t.nCols} · парсер: ${t.parserUsed}`}
            >
              <Table2 size={13} />
              Таблица {t.tableIndex + 1}
              {t.corrected && (
                <span className="ml-1 rounded bg-verified/20 px-1 text-[10px] text-verified">
                  исправлено v{t.currentVersion}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {docId && !busy && tables.length === 0 && (
        <div className="rounded-md border border-line bg-surface/40 px-3 py-2 text-sm text-muted">
          В этом документе нет распознанных таблиц.
        </div>
      )}

      {/* Editable grid */}
      {lineage && tableIndex !== null && (
        <div className="mt-2 rounded-md border border-line bg-surface/40 p-4">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
              <Pencil size={14} className="text-copper" />
              Правка таблицы {tableIndex + 1}
            </span>
            <span className="chip text-nickel" title="Действующая версия">
              версия v{lineage.current.version} · {lineage.current.parserUsed}
            </span>
            {original && (
              <span className="chip text-faint" title="Парсер, создавший исходник">
                исходник: {original.parserUsed || original.baseParser || 'parser'}
              </span>
            )}
          </div>

          {!canCorrect && (
            <div className="mb-3 rounded-md border border-gap/40 bg-gap/10 px-3 py-2 text-xs text-gap">
              Ваша роль может просматривать, но не сохранять правки таблиц.
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-xs">
              <tbody>
                {draft.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, c) => (
                      <td key={c} className="border border-line p-0">
                        <input
                          value={cell}
                          disabled={!canCorrect}
                          onChange={(e) => editCell(r, c, e.target.value)}
                          className={`w-full min-w-[6rem] bg-transparent px-2 py-1 text-ink outline-none focus:bg-copper/10 ${
                            r === 0 ? 'font-medium' : ''
                          }`}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {canCorrect && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                onClick={addRow}
                className="chip flex items-center gap-1.5 text-nickel hover:text-copper"
              >
                + строка
              </button>
              <button
                onClick={resetDraft}
                disabled={!dirty}
                className="chip flex items-center gap-1.5 text-nickel hover:text-copper disabled:opacity-40"
              >
                <RotateCcw size={13} /> сбросить
              </button>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Причина правки (необязательно)"
                className="flex-1 min-w-[12rem] rounded-md border border-line bg-surface/60 px-3 py-1.5 text-sm text-ink outline-none focus:border-copper/50"
              />
              <button
                onClick={() => void submit()}
                disabled={!dirty || saving}
                className="chip flex items-center gap-1.5 border-copper/40 text-copper hover:bg-copper/10 disabled:opacity-40"
              >
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                Сохранить как новую версию
              </button>
            </div>
          )}

          {toast && (
            <div className="mt-3 flex items-center gap-2 rounded-md border border-verified/40 bg-verified/10 px-3 py-2 text-sm text-verified">
              <CheckCircle2 size={14} /> {toast}
            </div>
          )}

          {/* Version lineage */}
          <div className="mt-5">
            <div className="mb-2 flex items-center gap-1.5 text-xs text-muted">
              <History size={13} /> История версий ({lineage.versionCount})
            </div>
            <ul className="space-y-1">
              {lineage.versions
                .slice()
                .reverse()
                .map((v) => (
                  <li
                    key={v.version}
                    className="flex flex-wrap items-center gap-2 rounded border border-line bg-surface/30 px-3 py-1.5 text-xs"
                  >
                    <span className="font-mono text-copper">v{v.version}</span>
                    <span className="flex items-center gap-1 text-nickel">
                      {v.version === 0 ? <FileText size={12} /> : <Pencil size={12} />}
                      {v.corrected ? 'ручная правка' : 'исходник парсера'}
                    </span>
                    <span className="text-faint">parser_used={v.parserUsed}</span>
                    {v.author && <span className="text-faint">· {v.author}</span>}
                    {v.reason && <span className="italic text-muted">· «{v.reason}»</span>}
                    {v.version === lineage.current.version && (
                      <span className="ml-auto rounded bg-copper/20 px-1.5 text-[10px] text-copper">
                        действующая
                      </span>
                    )}
                  </li>
                ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
