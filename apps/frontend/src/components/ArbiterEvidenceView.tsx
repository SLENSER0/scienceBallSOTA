import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Award,
  CircleOff,
  Gavel,
  Loader2,
  Ruler,
  ShieldCheck,
  Sparkles,
  Split,
} from 'lucide-react';

// §15.4 evidential arbiter UI. Self-contained (no api.ts edits): talks to the
// arbiter-evidence router directly with the same session-auth convention as api.ts.
// Shows which measurement is likely-correct — ranked by source quality (evidence
// strength / review status / confidence / OCR) — and proves a genuine conflict by
// laying the sides' confidence intervals on one axis (non-overlap = real conflict).

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

interface ContradictionRow {
  id: string;
  name: string;
  status: string | null;
  values: number[];
  unit: string | null;
  material: string | null;
  spread: number;
}

interface QualityBreakdown {
  strength: number;
  review: number;
  confidence: number;
  ocr: number;
  score: number;
}

interface Side {
  claim_id: string;
  value: number | null;
  unit: string | null;
  property: string | null;
  confidence: number | null;
  review_status: string | null;
  evidence_strength: string | null;
  evidence_rank: number;
  ocr_quality: number | null;
  year: number | null;
  country: string | null;
  practice: string | null;
  evidence: string | null;
  evidence_count: number;
  ci_low: number | null;
  ci_high: number | null;
  ci_source: string;
  quality: QualityBreakdown;
  quality_score: number;
  rank?: number;
  likely_correct?: boolean;
}

interface IntervalPair {
  a: string;
  b: string;
  overlap: boolean;
  disjoint: boolean;
}
interface IntervalsPayload {
  axis_min: number | null;
  axis_max: number | null;
  unit: string | null;
  pairs: IntervalPair[];
  any_disjoint: boolean;
}

interface Arbitration {
  id: string;
  name: string;
  status: string | null;
  property?: string | null;
  unit?: string | null;
  sides: Side[];
  likely_correct_id: string | null;
  verdict_basis: string;
  subtype: string;
  severity: number;
  reasons: string[];
  intervals: IntervalsPayload;
  note?: string;
}

const BASIS_LABEL: Record<string, string> = {
  evidence_strength: 'по качеству источника (evidence strength)',
  review_status: 'по статусу проверки (review status)',
  confidence: 'по уверенности экстрактора (confidence)',
  ocr_quality: 'по качеству OCR',
  source_quality: 'по совокупному качеству источника',
  tie: 'ничья — стороны равнозначны',
  insufficient: 'недостаточно данных',
};

const SUBTYPE_LABEL: Record<string, string> = {
  numeric_divergence: 'числовое расхождение',
  ci_disjoint: 'непересекающиеся доверит. интервалы',
  effect_direction: 'противоположный эффект',
  none: 'нет противоречия',
};

const CI_SOURCE_LABEL: Record<string, string> = {
  ci: 'доверит. интервал',
  std: 'value ± std',
  minmax: 'value_min..value_max',
  point: 'точечная оценка',
  none: '—',
};

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '');
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

// A labelled 0..1 quality bar (one provenance signal).
function QualityBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between text-[11px] text-faint">
        <span>{label}</span>
        <span className="font-mono">{pct(value)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-line/40">
        <div
          className="h-full rounded-full bg-copper/70"
          style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
        />
      </div>
    </div>
  );
}

// The interval axis: each side is a horizontal bar spanning [ci_low, ci_high]
// on a shared scale; the winner is copper, others muted. Non-overlap is the proof.
function IntervalAxis({ arb }: { arb: Arbitration }) {
  const { axis_min, axis_max } = arb.intervals;
  const bounded = arb.sides.filter((s) => s.ci_low !== null && s.ci_high !== null);
  if (axis_min === null || axis_max === null || bounded.length === 0) {
    return <div className="text-xs text-faint">Нет числовых интервалов для визуализации.</div>;
  }
  const lo = axis_min;
  const hi = axis_max;
  const span = hi - lo || 1;
  const pos = (v: number) => ((v - lo) / span) * 100;

  return (
    <div className="space-y-2">
      {bounded.map((s) => {
        const left = pos(s.ci_low as number);
        const width = Math.max(1.5, pos(s.ci_high as number) - left);
        const isPoint = s.ci_source === 'point';
        const win = s.likely_correct;
        return (
          <div key={s.claim_id} className="flex items-center gap-2">
            <div className="w-16 truncate text-[11px] text-faint" title={s.claim_id}>
              {fmt(s.value)} {s.unit ?? ''}
            </div>
            <div className="relative h-5 flex-1 rounded bg-line/20">
              <div
                className={`absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full ${
                  win ? 'bg-copper' : 'bg-slate-400/60'
                } ${isPoint ? 'ring-2 ring-inset' : ''}`}
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`[${fmt(s.ci_low)}, ${fmt(s.ci_high)}] · ${
                  CI_SOURCE_LABEL[s.ci_source] ?? s.ci_source
                }`}
              />
            </div>
          </div>
        );
      })}
      <div className="flex justify-between pl-[4.5rem] font-mono text-[10px] text-faint">
        <span>{fmt(lo)}</span>
        <span>
          {fmt(hi)} {arb.intervals.unit ?? ''}
        </span>
      </div>
    </div>
  );
}

function SideCard({ side }: { side: Side }) {
  const win = side.likely_correct;
  return (
    <div
      className={`panel p-4 ${win ? 'border-copper/60 bg-copper/[0.04]' : 'border-line/40'}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-display text-lg text-ink">
            {fmt(side.value)} {side.unit ?? ''}
          </span>
          {win && (
            <span className="inline-flex items-center gap-1 rounded-full bg-copper/15 px-2 py-0.5 text-[11px] font-medium text-copper">
              <Award size={12} /> likely-correct
            </span>
          )}
        </div>
        <span className="text-xs text-faint">#{side.rank}</span>
      </div>

      <div className="mb-3 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-faint">
        {side.evidence_strength && <span>источник: {side.evidence_strength}</span>}
        {side.review_status && <span>проверка: {side.review_status}</span>}
        {side.confidence !== null && <span>conf: {fmt(side.confidence)}</span>}
        {side.ocr_quality !== null && <span>OCR: {pct(side.ocr_quality)}</span>}
        {side.year && <span>{side.year}</span>}
        {side.country && <span>{side.country}</span>}
        <span>ев.: {side.evidence_count}</span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
        <QualityBar label="источник" value={side.quality.strength} />
        <QualityBar label="проверка" value={side.quality.review} />
        <QualityBar label="уверенность" value={side.quality.confidence} />
        <QualityBar label="OCR" value={side.quality.ocr} />
      </div>

      <div className="flex items-center justify-between border-t border-line/40 pt-2">
        <span className="text-[11px] text-faint">
          интервал {CI_SOURCE_LABEL[side.ci_source] ?? side.ci_source}:{' '}
          <span className="font-mono">
            [{fmt(side.ci_low)}, {fmt(side.ci_high)}]
          </span>
        </span>
        <span className="text-sm font-semibold text-copper">
          качество {pct(side.quality_score)}
        </span>
      </div>

      {side.evidence && (
        <p className="mt-2 border-l-2 border-line/50 pl-2 text-xs italic text-faint">
          «{side.evidence}»
        </p>
      )}
    </div>
  );
}

export function ArbiterEvidenceView() {
  const [selected, setSelected] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ['arbiter-evidence-list'],
    queryFn: () =>
      apiGet<{ contradictions: ContradictionRow[] }>(
        '/api/v1/arbiter-evidence/contradictions?limit=40',
      ),
  });

  const rows = useMemo(() => list.data?.contradictions ?? [], [list.data]);

  useEffect(() => {
    if (!selected && rows.length > 0) setSelected(rows[0].id);
  }, [rows, selected]);

  const arb = useQuery({
    queryKey: ['arbiter-evidence', selected],
    queryFn: () =>
      apiGet<Arbitration>(`/api/v1/arbiter-evidence/${encodeURIComponent(selected as string)}`),
    enabled: !!selected,
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">Доказательный арбитр · §15.4</div>
        <h2 className="mb-1 flex items-center gap-2 font-display text-2xl font-semibold">
          <Gavel size={22} className="text-copper" /> Арбитр: какое измерение вероятно верно
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Детерминированный арбитраж противоречий: стороны ранжируются по качеству источника
          (evidence strength → review status → confidence → OCR), а доверительные интервалы
          выкладываются на общую ось — <b>непересечение интервалов</b> служит доказательством
          настоящего конфликта, а не голословным вердиктом. Без LLM: результат стабилен и
          доступен даже когда агент-арбитр офлайн.
        </p>

        <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
          {/* Contradiction list */}
          <div className="panel max-h-[70vh] overflow-y-auto p-0">
            <div className="border-b border-line/60 px-3 py-2 text-xs uppercase text-faint">
              Противоречия {rows.length > 0 && `(${rows.length})`}
            </div>
            {list.isLoading && (
              <div className="flex items-center gap-2 px-3 py-3 text-sm text-faint">
                <Loader2 size={15} className="animate-spin text-copper" /> загрузка…
              </div>
            )}
            {list.isError && (
              <div className="px-3 py-3 text-sm text-red-400">
                Не удалось загрузить список противоречий.
              </div>
            )}
            {!list.isLoading && rows.length === 0 && (
              <div className="flex items-center gap-2 px-3 py-3 text-sm text-faint">
                <CircleOff size={15} /> противоречий не найдено
              </div>
            )}
            {rows.map((r) => {
              const active = r.id === selected;
              return (
                <button
                  key={r.id}
                  onClick={() => setSelected(r.id)}
                  className={`block w-full border-b border-line/30 px-3 py-2 text-left text-sm ${
                    active ? 'bg-copper/10' : 'hover:bg-line/10'
                  }`}
                >
                  <div className="truncate text-ink">{r.name}</div>
                  <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] text-faint">
                    {r.material && <span>{r.material}</span>}
                    {r.values.length >= 2 && (
                      <span className="font-mono">
                        {fmt(Math.min(...r.values))}…{fmt(Math.max(...r.values))} {r.unit ?? ''}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Arbitration detail */}
          <div>
            {arb.isLoading && (
              <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
                <Loader2 size={15} className="animate-spin text-copper" /> арбитраж…
              </div>
            )}
            {arb.isError && (
              <div className="panel border-red-500/40 p-4 text-sm text-red-400">
                Ошибка арбитража: {(arb.error as Error).message}
              </div>
            )}
            {arb.data && (
              <div className="space-y-5">
                {/* Verdict banner */}
                <div
                  className={`panel p-4 ${
                    arb.data.likely_correct_id ? 'border-copper/50' : 'border-line/50'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <Sparkles size={22} className="mt-0.5 text-copper" />
                    <div className="flex-1">
                      <div className="font-display text-lg text-ink">{arb.data.name}</div>
                      {arb.data.likely_correct_id ? (
                        <div className="text-sm text-faint">
                          Вероятно верная сторона выбрана{' '}
                          <b className="text-ink">
                            {BASIS_LABEL[arb.data.verdict_basis] ?? arb.data.verdict_basis}
                          </b>
                          .
                        </div>
                      ) : (
                        <div className="text-sm text-faint">
                          {arb.data.note ??
                            'Стороны равнозначны по качеству — однозначного лидера нет.'}
                        </div>
                      )}
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        <span className="rounded bg-line/30 px-2 py-0.5 text-faint">
                          тип: {SUBTYPE_LABEL[arb.data.subtype] ?? arb.data.subtype}
                        </span>
                        {arb.data.severity > 0 && (
                          <span className="rounded bg-line/30 px-2 py-0.5 text-faint">
                            серьёзность {pct(arb.data.severity)}
                          </span>
                        )}
                        <span
                          className={`inline-flex items-center gap-1 rounded px-2 py-0.5 ${
                            arb.data.intervals.any_disjoint
                              ? 'bg-red-500/15 text-red-400'
                              : 'bg-emerald-500/15 text-emerald-400'
                          }`}
                        >
                          {arb.data.intervals.any_disjoint ? (
                            <>
                              <Split size={12} /> интервалы не пересекаются
                            </>
                          ) : (
                            <>
                              <ShieldCheck size={12} /> интервалы пересекаются
                            </>
                          )}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Interval axis */}
                <div className="panel p-4">
                  <h3 className="mb-3 flex items-center gap-2 font-display text-base">
                    <Ruler size={16} className="text-copper" /> Пересечение доверительных
                    интервалов
                  </h3>
                  <IntervalAxis arb={arb.data} />
                  <p className="mt-3 text-xs text-faint">
                    {arb.data.intervals.any_disjoint
                      ? 'Интервалы не перекрываются — расхождение не объясняется погрешностью, конфликт настоящий.'
                      : 'Интервалы перекрываются — значения статистически совместимы, вероятна легитимная вариативность.'}
                  </p>
                </div>

                {/* Reasons */}
                {arb.data.reasons.length > 0 && (
                  <div className="panel p-4">
                    <h3 className="mb-2 font-display text-base">Доводы эвристик (§15.4)</h3>
                    <ul className="space-y-1 text-sm text-faint">
                      {arb.data.reasons.map((r, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-copper">•</span>
                          <span className="font-mono text-xs">{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Sides */}
                <div>
                  <h3 className="mb-2 font-display text-base">
                    Стороны конфликта (ранжированы по качеству источника)
                  </h3>
                  <div className="grid gap-3 md:grid-cols-2">
                    {arb.data.sides.map((s) => (
                      <SideCard key={s.claim_id} side={s} />
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
