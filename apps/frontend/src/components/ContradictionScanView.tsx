import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { GitCompareArrows, Loader2, Radar, Scale, Stamp, CheckCircle2, ChevronRight } from 'lucide-react';

// Систематическое обнаружение противоречий для арбитра (§13.15).
//
// В отличие от вкладки «Противоречия (арбитр)», которая показывает УЖЕ
// материализованные узлы :Contradiction, этот экран прогоняет систематический скан
// живого графа: группирует все measurement'ы по ключу (material, regime, property) и
// находит расходящиеся значения — конфликты, которые ещё НЕ выражены узлом графа.
// Каждый кандидат — first-class вход для агента-арбитра: у него стабильный id,
// провенанс обеих сторон и вердикт эвристики §15.4 (subtype / severity / сильнейшая
// сторона). Кнопка «Материализовать» фиксирует кандидата как узел :Contradiction —
// после чего его подхватывают агент-арбитр (analyze) и разрешение куратором (resolve).

type Side = {
  claim_id: string;
  value: number | null;
  unit: string | null;
  property: string | null;
  practice: string | null;
  year: number | null;
  country: string | null;
  confidence: number | null;
  evidence: string | null;
  source_id: string | null;
};

type ScanCandidate = {
  id: string;
  material: string;
  regime: string;
  property: string;
  name: string;
  values: number[];
  unit: string | null;
  spread: number;
  sides_count: number;
  subtype: string;
  severity: number;
  likely_correct_id: string | null;
  reasons: string[];
  materialized: boolean;
  sides: Side[];
};

type ScanResponse = { count: number; materialized: number; contradictions: ScanCandidate[] };

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

async function csFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

const SUBTYPE: Record<string, { ru: string; cls: string }> = {
  effect_direction: { ru: 'обратный эффект', cls: 'text-contradiction border-contradiction/40' },
  ci_disjoint: { ru: 'непересек. интервалы', cls: 'text-gap border-gap/40' },
  numeric_divergence: { ru: 'расхождение значений', cls: 'text-copper border-copper/40' },
};

const PRACTICE: Record<string, string> = {
  russia: 'отеч.',
  cis: 'СНГ',
  foreign: 'заруб.',
  global: 'межд.',
};

function sevColor(sev: number): string {
  if (sev >= 0.66) return '226, 84, 61';
  if (sev >= 0.33) return '184, 115, 51';
  return '138, 148, 158';
}

export function ContradictionScanView() {
  const qc = useQueryClient();
  const [sel, setSel] = useState<string | null>(null);

  const scan = useQuery({
    queryKey: ['contradiction-scan'],
    queryFn: () => csFetch<ScanResponse>('/api/v1/contradiction-scan?limit=1500'),
  });

  const materialize = useMutation({
    mutationFn: (cid: string) =>
      csFetch(`/api/v1/contradiction-scan/${encodeURIComponent(cid)}/materialize`, {
        method: 'POST',
        body: JSON.stringify({}),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contradiction-scan'] }),
  });

  const items = scan.data?.contradictions ?? [];
  const current = items.find((c) => c.id === sel) ?? null;

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[360px_1fr]">
      {/* Left: scan results list */}
      <aside className="flex min-h-0 flex-col border-r border-line bg-graphite/40">
        <div className="border-b border-line px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-nickel">
            <Radar size={15} className="text-copper" /> Скан противоречий
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-faint">
            конфликты по (материал · режим · свойство) · {items.length}
            {scan.data ? ` · ${scan.data.materialized} материализовано` : ''}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {scan.isLoading ? (
            <div className="flex items-center gap-2 p-3 font-mono text-[11px] text-faint">
              <Loader2 size={13} className="animate-spin text-copper" /> сканирую граф…
            </div>
          ) : scan.isError ? (
            <div className="p-3 font-mono text-[11px] text-contradiction">ошибка скана</div>
          ) : items.length === 0 ? (
            <div className="p-3 font-mono text-[11px] text-faint">
              систематических конфликтов не найдено
            </div>
          ) : (
            items.map((c) => {
              const st = SUBTYPE[c.subtype] ?? SUBTYPE.numeric_divergence;
              return (
                <button
                  key={c.id}
                  onClick={() => setSel(c.id)}
                  className={`mb-1.5 flex w-full flex-col gap-1 rounded border px-3 py-2 text-left transition ${
                    sel === c.id
                      ? 'border-copper/60 bg-copper/10'
                      : 'border-line bg-graphite/60 hover:border-copper/30'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] text-nickel">{c.material}</span>
                    {c.materialized ? (
                      <CheckCircle2 size={13} className="shrink-0 text-verified" />
                    ) : (
                      <ChevronRight size={13} className="shrink-0 text-faint" />
                    )}
                  </div>
                  <div className="truncate font-mono text-[10px] text-faint">
                    {c.property} @ {c.regime}
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded border px-1.5 py-0.5 font-mono text-[9px] ${st.cls}`}
                    >
                      {st.ru}
                    </span>
                    <span
                      className="rounded px-1.5 py-0.5 font-mono text-[9px]"
                      style={{
                        color: `rgb(${sevColor(c.severity)})`,
                        background: `rgba(${sevColor(c.severity)}, 0.12)`,
                      }}
                    >
                      severity {c.severity.toFixed(2)}
                    </span>
                    <span className="font-mono text-[9px] text-faint">{c.sides_count} стор.</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* Right: candidate detail */}
      <section className="min-h-0 overflow-y-auto p-6">
        {!current ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-faint">
            <GitCompareArrows size={30} className="opacity-40" />
            <div className="font-mono text-[11px]">
              выберите кандидата, чтобы увидеть стороны конфликта
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl">
            <div className="mb-1 flex items-center gap-2">
              <Scale size={18} className="text-copper" />
              <h2 className="text-lg text-nickel">{current.material}</h2>
            </div>
            <div className="mb-4 font-mono text-[11px] text-faint">
              {current.property} @ {current.regime} · разброс {current.spread}
              {current.unit ? ` ${current.unit}` : ''}
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10px] text-faint">
                вердикт эвристики §15.4:
              </span>
              {(() => {
                const st = SUBTYPE[current.subtype] ?? SUBTYPE.numeric_divergence;
                return (
                  <span className={`rounded border px-2 py-0.5 font-mono text-[10px] ${st.cls}`}>
                    {st.ru}
                  </span>
                );
              })()}
              <span
                className="rounded px-2 py-0.5 font-mono text-[10px]"
                style={{
                  color: `rgb(${sevColor(current.severity)})`,
                  background: `rgba(${sevColor(current.severity)}, 0.12)`,
                }}
              >
                severity {current.severity.toFixed(2)}
              </span>
              {current.materialized ? (
                <span className="ml-auto flex items-center gap-1 rounded border border-verified/40 px-2 py-0.5 font-mono text-[10px] text-verified">
                  <CheckCircle2 size={12} /> материализовано
                </span>
              ) : (
                <button
                  onClick={() => materialize.mutate(current.id)}
                  disabled={materialize.isPending}
                  className="ml-auto flex items-center gap-1.5 rounded border border-copper/50 bg-copper/10 px-3 py-1 font-mono text-[10px] text-copper transition hover:bg-copper/20 disabled:opacity-50"
                >
                  {materialize.isPending ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Stamp size={12} />
                  )}
                  Материализовать для арбитра
                </button>
              )}
            </div>

            {current.reasons.length > 0 && (
              <ul className="mb-5 space-y-1">
                {current.reasons.map((r, i) => (
                  <li key={i} className="font-mono text-[10px] text-nickel">
                    · {r}
                  </li>
                ))}
              </ul>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              {current.sides.map((s) => {
                const winner = s.claim_id === current.likely_correct_id;
                return (
                  <div
                    key={s.claim_id}
                    className={`rounded border p-3 ${
                      winner ? 'border-verified/50 bg-verified/5' : 'border-line bg-graphite/40'
                    }`}
                  >
                    <div className="flex items-baseline justify-between">
                      <span className="text-base text-nickel">
                        {s.value}
                        {s.unit ? <span className="ml-1 text-[11px] text-faint">{s.unit}</span> : null}
                      </span>
                      {winner && (
                        <span className="font-mono text-[9px] text-verified">лучше обоснована</span>
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-faint">
                      {s.practice && <span>{PRACTICE[s.practice] ?? s.practice}</span>}
                      {s.year && <span>{s.year}</span>}
                      {s.country && <span>{s.country}</span>}
                      {s.confidence != null && <span>conf {Number(s.confidence).toFixed(2)}</span>}
                    </div>
                    {s.evidence && (
                      <div className="mt-2 border-l-2 border-line pl-2 text-[11px] leading-snug text-nickel/80">
                        «{s.evidence}»
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {materialize.isSuccess && materialize.variables === current.id && (
              <div className="mt-4 rounded border border-verified/40 bg-verified/5 px-3 py-2 font-mono text-[10px] text-verified">
                узел :Contradiction создан — доступен агенту-арбитру (analyze) и куратору (resolve)
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
