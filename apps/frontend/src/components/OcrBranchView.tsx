import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  FileWarning,
  Loader2,
  RefreshCw,
  ScanText,
  Upload,
} from 'lucide-react';

// §5.7 OCR-ветка для сканированных PDF (do_ocr / ocr_used).
// Сканы русских металлургических отчётов не имеют текстового слоя и молча
// выпадают из корпуса. Эта панель показывает, какие движки OCR доступны,
// прогоняет OCR-ветку для загруженного PDF (сканирован ли, применён ли OCR,
// сколько символов восстановлено) и оценивает размер «слепой зоны» по уже
// загруженным документам.

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

interface Engine {
  name: string;
  available: boolean;
  detail: string;
}
interface EnginesResp {
  engines: Engine[];
  any_available: boolean;
  active: string | null;
}
interface OcrDecision {
  needs_ocr: boolean;
  mean_chars_per_page: number;
  empty_page_fraction: number;
  reason: string;
}
interface OcrPage {
  page: number;
  pre_chars: number;
  post_chars: number;
  ocr_applied: boolean;
  recovered_chars: number;
}
interface AnalyzeResp {
  doc_name: string;
  is_scanned: boolean;
  ocr_used: boolean;
  engine: string;
  decision: OcrDecision;
  page_count: number;
  pre_chars_total: number;
  post_chars_total: number;
  recovered_chars: number;
  blind_spot: boolean;
  pages: OcrPage[];
  text_by_page?: Record<string, string>;
}
interface CorpusDoc {
  doc_name: string;
  class: 'text' | 'recovered' | 'blind_spot';
  is_scanned: boolean;
  ocr_used: boolean;
  engine: string;
  page_count: number;
  empty_page_fraction: number;
  recovered_chars: number;
}
interface CorpusResp {
  engine_available: boolean;
  totals: {
    documents: number;
    text: number;
    scanned: number;
    recovered: number;
    blind_spot: number;
    recovered_chars: number;
    recovery_rate: number | null;
  };
  documents: CorpusDoc[];
}

const CLASS_LABEL: Record<CorpusDoc['class'], string> = {
  text: 'Текстовый слой',
  recovered: 'Восстановлен OCR',
  blind_spot: 'Слепая зона',
};
const CLASS_COLOR: Record<CorpusDoc['class'], string> = {
  text: 'text-emerald-500',
  recovered: 'text-sky-500',
  blind_spot: 'text-amber-500',
};

export function OcrBranchView() {
  const [engines, setEngines] = useState<EnginesResp | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [includeText, setIncludeText] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResp | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [corpus, setCorpus] = useState<CorpusResp | null>(null);
  const [surveying, setSurveying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadEngines = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/ocr/engines', { headers: { ...authHeaders() } });
      if (res.ok) setEngines((await res.json()) as EnginesResp);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void loadEngines();
  }, [loadEngines]);

  const analyze = async () => {
    if (!file) return;
    setAnalyzing(true);
    setError(null);
    setAnalysis(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`/api/v1/ocr/analyze?include_text=${includeText}`, {
        method: 'POST',
        headers: { ...authHeaders() },
        body: form,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `${res.status} ${res.statusText}`);
      }
      setAnalysis((await res.json()) as AnalyzeResp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const survey = async () => {
    setSurveying(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/ocr/corpus', { headers: { ...authHeaders() } });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setCorpus((await res.json()) as CorpusResp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSurveying(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-800 dark:text-slate-100">
          <ScanText className="h-5 w-5 text-sky-500" />
          OCR-ветка сканированных PDF
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          §5.7 — сканы без текстового слоя (do_ocr) распознаются и всё равно
          попадают в граф; флаг <code>ocr_used</code> фиксируется в метаданных.
        </p>
      </header>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* OCR engines */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            <Cpu className="h-4 w-4" /> Движки OCR в этом развёртывании
          </h2>
          <button
            onClick={() => void loadEngines()}
            className="rounded-md p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            title="Обновить"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        {engines ? (
          <div className="flex flex-col gap-1.5">
            {engines.engines.map((e) => (
              <div key={e.name} className="flex items-center gap-2 text-sm">
                {e.available ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : (
                  <FileWarning className="h-4 w-4 text-slate-400" />
                )}
                <span className="font-mono text-slate-700 dark:text-slate-200">{e.name}</span>
                <span className="text-slate-400">— {e.detail}</span>
              </div>
            ))}
            {!engines.any_available && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                Ни один движок не установлен — сканы будут помечены как «слепая
                зона» (нужен OCR), но текстовый слой всё равно извлекается.
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm text-slate-400">Загрузка…</p>
        )}
      </section>

      {/* Analyze a single PDF */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
          <Upload className="h-4 w-4" /> Проверить PDF
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-sky-50 file:px-3 file:py-1.5 file:text-sky-700 hover:file:bg-sky-100 dark:text-slate-300 dark:file:bg-sky-950/50 dark:file:text-sky-300"
          />
          <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={includeText}
              onChange={(e) => setIncludeText(e.target.checked)}
            />
            {includeText ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            Показать восстановленный текст
          </label>
          <button
            onClick={() => void analyze()}
            disabled={!file || analyzing}
            className="ml-auto inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanText className="h-4 w-4" />}
            Анализ OCR-ветки
          </button>
        </div>

        {analysis && (
          <div className="mt-4 flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Сканирован" value={analysis.is_scanned ? 'да' : 'нет'} accent={analysis.is_scanned ? 'text-amber-500' : 'text-emerald-500'} />
              <Stat label="ocr_used" value={analysis.ocr_used ? 'true' : 'false'} accent={analysis.ocr_used ? 'text-sky-500' : 'text-slate-400'} />
              <Stat label="Движок" value={analysis.engine} />
              <Stat label="Восстановлено, симв." value={String(analysis.recovered_chars)} />
            </div>
            {analysis.blind_spot && (
              <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                Слепая зона: документ сканирован, но OCR не применён (нет движка) —
                установите tesseract/pytesseract, чтобы вернуть его в граф.
              </div>
            )}
            <p className="text-xs text-slate-500 dark:text-slate-400">{analysis.decision.reason}</p>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-400">
                  <tr>
                    <th className="py-1 pr-4">Стр.</th>
                    <th className="py-1 pr-4">Символов (до)</th>
                    <th className="py-1 pr-4">Символов (после)</th>
                    <th className="py-1 pr-4">OCR</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.pages.map((p) => (
                    <tr key={p.page} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1 pr-4 font-mono">{p.page}</td>
                      <td className="py-1 pr-4">{p.pre_chars}</td>
                      <td className="py-1 pr-4">{p.post_chars}</td>
                      <td className="py-1 pr-4">
                        {p.ocr_applied ? (
                          <span className="text-sky-500">+{p.recovered_chars}</span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {analysis.text_by_page && (
              <details className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <summary className="cursor-pointer text-sm text-slate-600 dark:text-slate-300">
                  Восстановленный текст ({Object.keys(analysis.text_by_page).length} стр.)
                </summary>
                <div className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-slate-600 dark:text-slate-400">
                  {Object.entries(analysis.text_by_page).map(([pg, txt]) => (
                    <div key={pg} className="mb-2">
                      <span className="text-slate-400">— стр. {pg} —</span>
                      {'\n'}
                      {txt}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </section>

      {/* Corpus blind-spot survey */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            <FileWarning className="h-4 w-4" /> Слепая зона корпуса (загруженные PDF)
          </h2>
          <button
            onClick={() => void survey()}
            disabled={surveying}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {surveying ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Прогнать
          </button>
        </div>

        {corpus && (
          <>
            <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Документов" value={String(corpus.totals.documents)} />
              <Stat label="Текстовых" value={String(corpus.totals.text)} accent="text-emerald-500" />
              <Stat label="Восстановлено" value={String(corpus.totals.recovered)} accent="text-sky-500" />
              <Stat label="Слепая зона" value={String(corpus.totals.blind_spot)} accent="text-amber-500" />
            </div>
            {corpus.documents.length === 0 ? (
              <p className="text-sm text-slate-400">
                Нет загруженных PDF. Загрузите документы через «Библиотеку», затем прогоните обзор.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase text-slate-400">
                    <tr>
                      <th className="py-1 pr-4">Документ</th>
                      <th className="py-1 pr-4">Класс</th>
                      <th className="py-1 pr-4">Стр.</th>
                      <th className="py-1 pr-4">Пустых стр.</th>
                      <th className="py-1 pr-4">ocr_used</th>
                    </tr>
                  </thead>
                  <tbody>
                    {corpus.documents.map((d) => (
                      <tr key={d.doc_name} className="border-t border-slate-100 dark:border-slate-800">
                        <td className="max-w-xs truncate py-1 pr-4 font-mono" title={d.doc_name}>
                          {d.doc_name}
                        </td>
                        <td className={`py-1 pr-4 ${CLASS_COLOR[d.class]}`}>{CLASS_LABEL[d.class]}</td>
                        <td className="py-1 pr-4">{d.page_count}</td>
                        <td className="py-1 pr-4">{Math.round(d.empty_page_fraction * 100)}%</td>
                        <td className="py-1 pr-4">{d.ocr_used ? 'true' : 'false'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800/50">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-lg font-semibold ${accent ?? 'text-slate-700 dark:text-slate-100'}`}>{value}</div>
    </div>
  );
}
