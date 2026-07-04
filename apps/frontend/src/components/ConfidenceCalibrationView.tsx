import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CircleCheck,
  Gauge,
  Info,
  Loader2,
  Play,
  ShieldQuestion,
} from 'lucide-react';

// §23.25 Confidence calibration. Self-contained (no api.ts edits): calls the
// confidence-calibration router directly with the same session-auth convention as
// api.ts. Shows a reliability diagram (predicted vs observed accuracy per bin), ECE /
// MCE / Brier, the honest over/under-confidence verdict, the post-hoc calibrator
// remap, and honest word-labels (high confidence / needs review / conflicting /
// unsupported / estimated) instead of bare percentages.

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

interface ReliabilityBin {
  lo: number;
  hi: number;
  count: number;
  avg_confidence: number;
  accuracy: number;
  gap: number;
  direction: string;
  honest_label: string | null;
}
interface Verdict {
  well_calibrated: boolean;
  ece: number;
  ece_budget: number;
  bias: string;
  bias_magnitude: number;
}
interface CalibratorKnot {
  raw: number;
  calibrated: number;
}
interface CalExample {
  raw: number;
  calibrated: number;
  honest_label: string;
}
interface ReportResponse {
  source: string;
  source_desc: string;
  n: number;
  n_bins: number;
  golden_size: number;
  used_queries: number;
  ece: number;
  mce: number;
  brier: number;
  bins: ReliabilityBin[];
  verdict: Verdict;
  calibrator: CalibratorKnot[];
  calibrated_examples: CalExample[];
  honest_notes: string[];
  warnings: string[];
  elapsed_ms: number;
}
interface LabelEntry {
  label: string;
  ru: string;
  meaning: string;
}
interface LabelsResponse {
  labels: LabelEntry[];
  thresholds: { high: number; review: number; low: number };
  honest_notes: string[];
}
interface TranslateOut {
  confidence: number;
  calibrated_confidence: number | null;
  honest_label: string;
}
interface TranslateResponse {
  results: TranslateOut[];
  thresholds: { high: number; review: number; low: number };
  calibrated: boolean;
}

function fmt(v: number, d = 4): string {
  if (v === undefined || v === null || Number.isNaN(v)) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(d).replace(/0+$/, '').replace(/\.$/, '');
}
function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

// Honest label → colour class (matches the app palette).
const LABEL_TONE: Record<string, string> = {
  'high confidence': 'text-emerald-500',
  'needs review': 'text-amber-500',
  estimated: 'text-sky-500',
  conflicting: 'text-orange-500',
  unsupported: 'text-rose-500',
};
const DIR_COLOR: Record<string, string> = {
  overconfident: '#f43f5e', // rose — claims more than it delivers
  underconfident: '#0ea5e9', // sky — delivers more than it claims
  calibrated: '#10b981', // emerald — matches
  empty: '#9ca3af',
};

// ---------------------------------------------------------------------------
// Reliability diagram (inline SVG): predicted confidence (x) vs observed
// accuracy (y). The dashed diagonal is perfect calibration; each populated bin
// is a dot at (avg_confidence, accuracy) sized by its count; the calibrator step
// curve shows the raw→calibrated remap.
// ---------------------------------------------------------------------------
function ReliabilityDiagram({ report }: { report: ReportResponse }) {
  const W = 460;
  const H = 460;
  const pad = 44;
  const x = (v: number) => pad + v * (W - 2 * pad);
  const y = (v: number) => H - pad - v * (H - 2 * pad);
  const populated = report.bins.filter((b) => b.count > 0);
  const maxCount = Math.max(1, ...populated.map((b) => b.count));
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full max-w-[460px]"
      role="img"
      aria-label="Reliability diagram: predicted confidence vs observed accuracy"
    >
      {/* grid + ticks */}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} y1={y(0)} x2={x(t)} y2={y(1)} stroke="currentColor" opacity={0.08} />
          <line x1={x(0)} y1={y(t)} x2={x(1)} y2={y(t)} stroke="currentColor" opacity={0.08} />
          <text x={x(t)} y={y(0) + 16} textAnchor="middle" className="fill-current text-faint" fontSize={10}>
            {t}
          </text>
          <text x={x(0) - 8} y={y(t) + 3} textAnchor="end" className="fill-current text-faint" fontSize={10}>
            {t}
          </text>
        </g>
      ))}
      {/* perfect-calibration diagonal */}
      <line
        x1={x(0)}
        y1={y(0)}
        x2={x(1)}
        y2={y(1)}
        stroke="currentColor"
        strokeDasharray="5 5"
        opacity={0.4}
      />
      {/* calibrator step curve (raw → calibrated / empirical accuracy) */}
      {report.calibrator.length > 1 && (
        <polyline
          fill="none"
          stroke="#6366f1"
          strokeWidth={1.5}
          opacity={0.7}
          points={report.calibrator.map((k) => `${x(k.raw)},${y(k.calibrated)}`).join(' ')}
        />
      )}
      {/* gap lines from diagonal to each bin's observed point */}
      {populated.map((b) => (
        <line
          key={`gap-${b.lo}`}
          x1={x(b.avg_confidence)}
          y1={y(b.avg_confidence)}
          x2={x(b.avg_confidence)}
          y2={y(b.accuracy)}
          stroke={DIR_COLOR[b.direction] ?? DIR_COLOR.empty}
          strokeWidth={1}
          opacity={0.35}
        />
      ))}
      {/* observed points, radius ∝ sqrt(count) */}
      {populated.map((b) => (
        <circle
          key={`pt-${b.lo}`}
          cx={x(b.avg_confidence)}
          cy={y(b.accuracy)}
          r={4 + 9 * Math.sqrt(b.count / maxCount)}
          fill={DIR_COLOR[b.direction] ?? DIR_COLOR.empty}
          fillOpacity={0.75}
          stroke="white"
          strokeWidth={0.75}
        >
          <title>
            {`bin [${fmt(b.lo)}, ${fmt(b.hi)}) · n=${b.count}\npredicted ${pct(
              b.avg_confidence,
            )} → observed ${pct(b.accuracy)}\n${b.direction}`}
          </title>
        </circle>
      ))}
      {/* axis labels */}
      <text x={W / 2} y={H - 6} textAnchor="middle" className="fill-current text-faint" fontSize={11}>
        Заявленная уверенность (predicted)
      </text>
      <text
        x={14}
        y={H / 2}
        textAnchor="middle"
        transform={`rotate(-90 14 ${H / 2})`}
        className="fill-current text-faint"
        fontSize={11}
      >
        Фактическая точность (observed)
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Confidence → honest label translator
// ---------------------------------------------------------------------------
function Translator() {
  const [conf, setConf] = useState(0.83);
  const [hasConflict, setHasConflict] = useState(false);
  const [hasEvidence, setHasEvidence] = useState(true);
  const [isEstimated, setIsEstimated] = useState(false);

  const run = useMutation({
    mutationFn: () =>
      apiPost<TranslateResponse>('/api/v1/confidence-calibration/translate', {
        items: [
          {
            confidence: conf,
            has_conflict: hasConflict,
            has_evidence: hasEvidence,
            is_estimated: isEstimated,
          },
        ],
        calibrate: true,
      }),
  });
  const out = run.data?.results?.[0];

  return (
    <div className="panel p-4">
      <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
        <ShieldQuestion size={16} /> Перевод числа → честная метка
      </div>
      <p className="mb-3 text-xs text-faint">
        Голый процент бессмыслен без калибровки и без сигналов. Введите заявленную уверенность и
        флаги — получите честную словесную метку и калиброванное значение.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-faint">confidence</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={conf}
            onChange={(e) => setConf(Math.max(0, Math.min(1, Number(e.target.value))))}
            className="w-24 rounded border border-line bg-transparent px-2 py-1 text-sm"
          />
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={hasConflict} onChange={(e) => setHasConflict(e.target.checked)} />
          конфликт
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={!hasEvidence} onChange={(e) => setHasEvidence(!e.target.checked)} />
          нет evidence
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={isEstimated} onChange={(e) => setIsEstimated(e.target.checked)} />
          оценка
        </label>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="btn-copper inline-flex items-center gap-1.5 px-3 py-1.5 text-sm"
        >
          {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          Перевести
        </button>
      </div>
      {out && (
        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          <span>
            метка:{' '}
            <span className={`font-semibold ${LABEL_TONE[out.honest_label] ?? ''}`}>
              {out.honest_label}
            </span>
          </span>
          <span className="text-faint">
            raw {pct(out.confidence)} → калибр.{' '}
            <span className="font-mono">
              {out.calibrated_confidence === null ? '—' : pct(out.calibrated_confidence)}
            </span>
          </span>
        </div>
      )}
      {run.isError && <div className="mt-2 text-sm text-rose-500">Ошибка перевода.</div>}
    </div>
  );
}

export function ConfidenceCalibrationView() {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const labels = useQuery({
    queryKey: ['calibration-labels'],
    queryFn: () => apiGet<LabelsResponse>('/api/v1/confidence-calibration/labels'),
  });
  const run = useMutation({
    mutationFn: () => apiGet<ReportResponse>('/api/v1/confidence-calibration/report'),
    onSuccess: (d) => setReport(d),
  });

  const tiles = useMemo(() => {
    if (!report) return [];
    return [
      { label: 'ECE', value: fmt(report.ece), hint: 'Expected Calibration Error — ниже лучше' },
      { label: 'MCE', value: fmt(report.mce), hint: 'худший разрыв по одному бину' },
      { label: 'Brier', value: fmt(report.brier), hint: 'средне-квадратичная ошибка' },
      { label: 'n пар', value: String(report.n), hint: '(confidence, label) над golden' },
    ];
  }, [report]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">confidence calibration · §23.25</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Калибровка уверенности</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Доказывает, что числа уверенности <em>откалиброваны</em>, а не просто выглядят убедительно.
          Reliability-диаграмма (заявленная уверенность vs фактическая точность по бинам), Expected
          Calibration Error и честные словесные метки вместо голых процентов. Источник — golden-набор
          (§18.6) над живым графом: для каждого запроса гибридный retrieval-score (§10.2) сопоставлен с
          тем, действительно ли кандидат релевантен.
        </p>

        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="btn-copper mb-5 inline-flex items-center gap-2 px-4 py-2 text-sm"
        >
          {run.isPending ? <Loader2 size={16} className="animate-spin" /> : <Gauge size={16} />}
          {report ? 'Пересчитать' : 'Построить reliability-диаграмму'}
        </button>
        {run.isPending && (
          <span className="ml-3 text-sm text-faint">
            прогон golden-retrieval над живым графом (несколько секунд)…
          </span>
        )}
        {run.isError && (
          <div className="mb-4 text-sm text-rose-500">Не удалось построить отчёт.</div>
        )}

        {report && (
          <>
            {/* verdict + metric tiles */}
            <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div
                className={`panel p-4 ${
                  report.verdict.well_calibrated ? 'ring-1 ring-emerald-500/40' : 'ring-1 ring-amber-500/40'
                }`}
              >
                <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                  {report.verdict.well_calibrated ? (
                    <CircleCheck size={16} className="text-emerald-500" />
                  ) : (
                    <AlertTriangle size={16} className="text-amber-500" />
                  )}
                  Вердикт
                </div>
                <div className="text-sm">
                  {report.verdict.well_calibrated ? 'откалибровано' : 'требует калибровки'} ·{' '}
                  <span className="font-semibold">{report.verdict.bias}</span>
                </div>
                <div className="mt-1 text-xs text-faint">
                  ECE {fmt(report.ece)} vs бюджет {fmt(report.verdict.ece_budget)}
                </div>
              </div>
              {tiles.map((t) => (
                <div key={t.label} className="panel p-4">
                  <div className="text-xs text-faint">{t.label}</div>
                  <div className="font-display text-2xl font-semibold">{t.value}</div>
                  <div className="mt-0.5 text-xs text-faint">{t.hint}</div>
                </div>
              ))}
            </div>

            {report.warnings.length > 0 && (
              <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                {report.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-amber-600 dark:text-amber-400">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {w}
                  </div>
                ))}
              </div>
            )}

            <div className="mb-4 grid gap-4 lg:grid-cols-[auto_1fr]">
              {/* diagram */}
              <div className="panel p-4">
                <div className="mb-2 text-sm font-semibold">Reliability-диаграмма</div>
                <ReliabilityDiagram report={report} />
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-faint">
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2 w-4 border-b-2 border-dashed" /> идеальная калибровка
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2 w-4" style={{ background: '#6366f1' }} /> калибратор (raw→calibrated)
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: DIR_COLOR.overconfident }} /> переоценка
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: DIR_COLOR.underconfident }} /> недооценка
                  </span>
                </div>
              </div>

              {/* per-bin table */}
              <div className="panel overflow-x-auto p-4">
                <div className="mb-2 text-sm font-semibold">Бины ({report.used_queries}/{report.golden_size} golden-запросов)</div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-faint">
                      <th className="py-1 pr-3">бин</th>
                      <th className="py-1 pr-3 text-right">n</th>
                      <th className="py-1 pr-3 text-right">предсказано</th>
                      <th className="py-1 pr-3 text-right">наблюдалось</th>
                      <th className="py-1 pr-3 text-right">разрыв</th>
                      <th className="py-1 pr-3">метка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.bins
                      .filter((b) => b.count > 0)
                      .map((b) => (
                        <tr key={b.lo} className="border-t border-line/50">
                          <td className="py-1 pr-3 font-mono text-xs">
                            [{fmt(b.lo)}, {fmt(b.hi)})
                          </td>
                          <td className="py-1 pr-3 text-right">{b.count}</td>
                          <td className="py-1 pr-3 text-right">{pct(b.avg_confidence)}</td>
                          <td className="py-1 pr-3 text-right font-semibold">{pct(b.accuracy)}</td>
                          <td
                            className="py-1 pr-3 text-right"
                            style={{ color: DIR_COLOR[b.direction] }}
                          >
                            {b.gap > 0 ? '+' : ''}
                            {pct(b.gap)}
                          </td>
                          <td className={`py-1 pr-3 ${LABEL_TONE[b.honest_label ?? ''] ?? ''}`}>
                            {b.honest_label ?? '—'}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                {report.calibrated_examples.length > 0 && (
                  <div className="mt-3 border-t border-line/50 pt-3">
                    <div className="mb-1 text-xs font-semibold text-faint">
                      Калибратор на примерах (raw → калиброванная уверенность):
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {report.calibrated_examples.map((e) => (
                        <span key={e.raw} className="rounded bg-surface px-2 py-1 text-xs">
                          {pct(e.raw)} → <span className="font-semibold">{pct(e.calibrated)}</span>{' '}
                          <span className={LABEL_TONE[e.honest_label] ?? ''}>{e.honest_label}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {/* honest labels legend + disclaimers (always available) */}
        {labels.data && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="panel p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Info size={16} /> Честные словесные метки
              </div>
              <ul className="space-y-2">
                {labels.data.labels.map((l) => (
                  <li key={l.label} className="text-sm">
                    <span className={`font-semibold ${LABEL_TONE[l.label] ?? ''}`}>{l.label}</span>{' '}
                    <span className="text-faint">({l.ru})</span>
                    <div className="text-xs text-faint">{l.meaning}</div>
                  </li>
                ))}
              </ul>
              <div className="mt-3 text-xs text-faint">
                Полосы: high ≥ {labels.data.thresholds.high} · review ≥ {labels.data.thresholds.review} ·
                low ≥ {labels.data.thresholds.low}
              </div>
            </div>
            <div className="flex flex-col gap-4">
              <div className="panel p-4">
                <div className="mb-2 text-sm font-semibold">Дисклеймеры (обязательны рядом с числом)</div>
                <ul className="space-y-1.5">
                  {labels.data.honest_notes.map((n, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-faint">
                      <span className="mt-0.5 text-amber-500">•</span> {n}
                    </li>
                  ))}
                </ul>
              </div>
              <Translator />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
