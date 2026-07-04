import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Gauge,
  Layers,
  Loader2,
  Play,
  Table,
} from 'lucide-react';

// §25.16 extraction-recall eval by modality. Self-contained (no api.ts edits): calls the
// extraction-recall-eval router directly with the same session-auth convention as api.ts.
// Turns confidence-of-absence into a measured number: a deterministic offline extractor
// runs over a modality-split gold set and reports recall per modality (table_row /
// catalog_row / chunk-prose), overall recall, blind spots and fact→evidence→modality
// attribution — with the §25.10 heuristic prior alongside each measured recall.

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

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

interface ModalityCount {
  modality: string;
  n_units: number;
  n_facts: number;
}
interface ConfigResponse {
  n_units: number;
  n_facts: number;
  modalities: ModalityCount[];
  default_blind_spot_at: number;
  note: string;
}

interface ModalityRow {
  modality: string;
  expected: number;
  extracted: number;
  recall: number;
  is_blind_spot: boolean;
  prior?: { offline?: number; llm?: number };
  recall_minus_prior_offline?: number;
}
interface AttributionRow {
  doc_id: string;
  modality: string;
  subject: string;
  property_name: string;
  value: number;
  unit: string;
  evidence: string;
  extracted: boolean;
}
interface RunResult {
  backend: string;
  extraction_run_id: string | null;
  n_units: number;
  by_modality: ModalityRow[];
  overall_recall: number;
  expected_total: number;
  extracted_total: number;
  blind_spots: string[];
  blind_spot_at: number;
  precision_note: string;
  attribution: AttributionRow[];
  markdown: string;
}

const MODALITY_META: Record<string, { label: string; icon: typeof Table }> = {
  table_row: { label: 'Таблицы (table_row)', icon: Table },
  catalog_row: { label: 'Каталог (catalog_row)', icon: Layers },
  chunk: { label: 'Проза (chunk)', icon: FileText },
};

function pct(v: number | undefined): string {
  if (v === undefined || v === null) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function recallColor(recall: number, blind: boolean): string {
  if (blind) return 'text-amber-400';
  if (recall >= 0.85) return 'text-emerald-400';
  return 'text-ink';
}

export function ExtractionRecallEvalView() {
  const [result, setResult] = useState<RunResult | null>(null);
  const [onlyMissed, setOnlyMissed] = useState(false);

  const cfg = useQuery({
    queryKey: ['extraction-recall-eval-config'],
    queryFn: () => apiGet<ConfigResponse>('/api/v1/extraction-recall-eval/config'),
  });
  const run = useMutation({
    mutationFn: () =>
      apiPost<RunResult>('/api/v1/extraction-recall-eval/run', { blind_spot_at: 0.5 }),
    onSuccess: (d) => setResult(d),
  });

  const attribution = (result?.attribution ?? []).filter((a) => !onlyMissed || !a.extracted);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">extraction-recall · §25.16</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Recall извлечения по модальностям
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Делает «слепое пятно» числом. Детерминированный offline-экстрактор (без LLM)
          прогоняется по модально-размеченному gold-набору и считает recall по каждой
          модальности (table_row / catalog_row / проза), overall и «слепые зоны», с
          атрибуцией факт → evidence → модальность. Структурированные строки читаются
          почти идеально; плотная проза требует LLM — её низкий recall и есть измеримое
          слепое пятно, которое питает калибровку confidence-of-absence (§25.11).
        </p>

        {/* Gold-set catalogue */}
        {cfg.data && (
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            {cfg.data.modalities.map((m) => {
              const meta = MODALITY_META[m.modality] ?? { label: m.modality, icon: Gauge };
              const Icon = meta.icon;
              return (
                <div key={m.modality} className="panel p-3">
                  <div className="flex items-center gap-2 font-display text-sm text-ink">
                    <Icon size={15} className="text-copper" /> {meta.label}
                  </div>
                  <div className="mt-1 text-xs text-faint">
                    {m.n_facts} фактов · {m.n_units} evidence-единиц
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="btn-copper flex items-center gap-2"
          >
            {run.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            {run.isPending ? 'Прогон eval…' : 'Запустить eval'}
          </button>
          {cfg.data && (
            <span className="text-xs text-faint">
              gold: {cfg.data.n_facts} фактов · {cfg.data.n_units} единиц · порог слепой
              зоны &lt; {cfg.data.default_blind_spot_at}
            </span>
          )}
        </div>

        {run.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка прогона: {(run.error as Error).message}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* Overall + blind-spot banner */}
            <div
              className={`panel flex items-center gap-3 p-4 ${
                result.blind_spots.length ? 'border-amber-500/40' : 'border-emerald-500/40'
              }`}
            >
              {result.blind_spots.length ? (
                <AlertTriangle size={28} className="text-amber-400" />
              ) : (
                <CheckCircle2 size={28} className="text-emerald-400" />
              )}
              <div>
                <div className="font-display text-lg text-ink">
                  Overall recall: {pct(result.overall_recall)} ({result.extracted_total}/
                  {result.expected_total} фактов)
                </div>
                <div className="text-sm text-faint">
                  {result.blind_spots.length ? (
                    <>
                      Слепые зоны (recall &lt; {result.blind_spot_at}):{' '}
                      <span className="text-amber-400">{result.blind_spots.join(', ')}</span>
                    </>
                  ) : (
                    'Слепых зон не обнаружено'
                  )}{' '}
                  · backend={result.backend}
                </div>
              </div>
            </div>

            {/* Per-modality recall vs prior */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <Gauge size={18} className="text-copper" /> Recall по модальностям vs prior §25.10
              </h3>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Модальность</th>
                      <th className="px-3 py-2 text-right">Ожидалось</th>
                      <th className="px-3 py-2 text-right">Извлечено</th>
                      <th className="px-3 py-2 text-right">Recall</th>
                      <th className="px-3 py-2 text-right">Prior (offline)</th>
                      <th className="px-3 py-2 text-right">Δ vs prior</th>
                      <th className="px-3 py-2 text-center">Слепая зона</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.by_modality.map((m) => (
                      <tr key={m.modality} className="border-b border-line/30">
                        <td className="px-3 py-2 text-ink">
                          {MODALITY_META[m.modality]?.label ?? m.modality}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {m.expected}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {m.extracted}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono font-bold ${recallColor(
                            m.recall,
                            m.is_blind_spot,
                          )}`}
                        >
                          {pct(m.recall)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {pct(m.prior?.offline)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {m.recall_minus_prior_offline === undefined
                            ? '—'
                            : `${m.recall_minus_prior_offline > 0 ? '+' : ''}${(
                                m.recall_minus_prior_offline * 100
                              ).toFixed(1)}%`}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {m.is_blind_spot ? (
                            <AlertTriangle size={15} className="inline text-amber-400" />
                          ) : (
                            <CheckCircle2 size={15} className="inline text-emerald-400" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-xs text-faint">{result.precision_note}</p>
            </div>

            {/* Attribution fact → evidence → modality */}
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 font-display text-lg">
                  <FileText size={18} className="text-copper" /> Атрибуция: факт → evidence →
                  модальность
                </h3>
                <label className="flex items-center gap-2 text-xs text-faint">
                  <input
                    type="checkbox"
                    checked={onlyMissed}
                    onChange={(e) => setOnlyMissed(e.target.checked)}
                  />
                  только пропущенные
                </label>
              </div>
              <div className="panel overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Статус</th>
                      <th className="px-3 py-2">Модальность</th>
                      <th className="px-3 py-2">Субъект</th>
                      <th className="px-3 py-2">Свойство</th>
                      <th className="px-3 py-2 text-right">Значение</th>
                      <th className="px-3 py-2">Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attribution.map((a, i) => (
                      <tr key={i} className="border-b border-line/30 align-top">
                        <td className="px-3 py-2">
                          {a.extracted ? (
                            <CheckCircle2 size={15} className="text-emerald-400" />
                          ) : (
                            <AlertTriangle size={15} className="text-amber-400" />
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-faint">{a.modality}</td>
                        <td className="px-3 py-2 text-ink">{a.subject}</td>
                        <td className="px-3 py-2 text-faint">{a.property_name}</td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {a.value} {a.unit}
                        </td>
                        <td className="max-w-md px-3 py-2 text-xs text-faint">{a.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
