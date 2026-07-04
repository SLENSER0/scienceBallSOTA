import { useEffect, useState } from 'react';
import { AlertTriangle, ShieldQuestion, Info } from 'lucide-react';

// §25.13 — «Честный no-data в чате». After the agent answers, its gaps are folded
// through the absence layer (POST /api/v1/chat/absence-self-check, read-only). When
// any gap is a `possible_miss` / `abstain` — or carries a high extractor-miss risk —
// this banner warns the reader that «возможно, факт есть, но извлечение его пропустило»
// instead of letting «тему не изучали» stand unchallenged. Genuine gaps stay quiet.

interface VerdictLabel {
  ru: string;
  en: string;
}

interface AnnotatedGap {
  absence_verdict: string;
  p_truly_absent?: number;
  p_extractor_missed?: number;
  extractor_miss_risk_pct: number;
  verdict_labels: VerdictLabel;
  hold_back: boolean;
  about?: { id: string; name: string }[];
  name?: string;
  property_name?: string;
}

interface Banner {
  severity: 'high' | 'info';
  title_ru: string;
  title_en: string;
  message_ru: string;
  message_en: string;
  n_hold_back: number;
  n_high_miss_risk: number;
  calibrated: boolean;
}

interface SelfCheck {
  n_gaps: number;
  n_genuine_gap: number;
  n_possible_miss: number;
  n_retracted: number;
  n_abstain: number;
  n_high_miss_risk: number;
  calibrated: boolean;
  warnings: string[];
}

interface SelfCheckResponse {
  self_check: SelfCheck;
  hold_back_count: number;
  banner: Banner | null;
  gaps: AnnotatedGap[];
}

// A gap as it arrives on the chat surface — any shape the backend can key off.
export type GapInput = Record<string, unknown>;

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

async function fetchSelfCheck(gaps: GapInput[]): Promise<SelfCheckResponse> {
  const res = await fetch('/api/v1/chat/absence-self-check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ gaps }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<SelfCheckResponse>;
}

// Only these verdicts must not be presented as unstudied (§25.13). Their chips
// carry the amber "hold-back" treatment; genuine gaps get a neutral chip.
const HOLD_BACK = new Set(['possible_miss', 'abstain']);

function gapTitle(g: AnnotatedGap): string {
  return g.about?.[0]?.name || g.name || g.property_name || 'ячейка';
}

export function ChatNoDataWarning({ gaps }: { gaps: GapInput[] }) {
  const [data, setData] = useState<SelfCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    if (!gaps || gaps.length === 0) {
      setData(null);
      return;
    }
    setLoading(true);
    setFailed(false);
    fetchSelfCheck(gaps)
      .then((r) => live && setData(r))
      .catch(() => live && setFailed(true))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [gaps]);

  if (loading)
    return (
      <div className="mt-2 flex items-center gap-2 text-[11px] text-faint">
        <ShieldQuestion size={13} className="animate-pulse text-copper" /> Проверка честности no-data…
      </div>
    );
  if (failed || !data || !data.banner) return null; // silent when the answer is safe

  const { banner, self_check: sc, gaps: annotated } = data;
  const critical = banner.severity === 'high';
  const held = annotated.filter((g) => HOLD_BACK.has(g.absence_verdict));

  return (
    <div
      className={`mt-3 rounded-md border p-3 text-sm ${
        critical
          ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
          : 'border-line bg-copper/5 text-nickel'
      }`}
    >
      <div className="mb-1 flex items-center gap-2 font-medium">
        {critical ? (
          <AlertTriangle size={15} className="shrink-0 text-amber-400" />
        ) : (
          <Info size={15} className="shrink-0 text-copper" />
        )}
        <span>{banner.title_ru}</span>
      </div>
      <p className="mb-2 text-[13px] leading-snug opacity-90">{banner.message_ru}</p>

      {held.length > 0 && (
        <ul className="mb-2 space-y-1">
          {held.slice(0, 6).map((g, i) => (
            <li key={i} className="flex items-center gap-2 text-[12px]">
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-amber-300">
                {g.verdict_labels.ru}
              </span>
              <span className="truncate text-nickel/90">{gapTitle(g)}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-faint">
                риск пропуска {g.extractor_miss_risk_pct}%
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2 text-[10px] text-faint">
        <span className="font-mono">
          пробелов: {sc.n_gaps} · реальных: {sc.n_genuine_gap} · возможный пропуск:{' '}
          {sc.n_possible_miss} · неопределённо: {sc.n_abstain}
          {sc.n_retracted > 0 ? ` · ретрагировано: ${sc.n_retracted}` : ''}
        </span>
        <span
          className={`ml-auto rounded px-1.5 py-0.5 font-mono uppercase tracking-wide ${
            sc.calibrated ? 'bg-emerald-500/15 text-emerald-300' : 'bg-nickel/10 text-faint'
          }`}
          title={
            sc.calibrated
              ? 'Оценка калибрована на gold-наборе'
              : 'Эвристическая оценка (нет калибровочного набора)'
          }
        >
          {sc.calibrated ? 'калибровано' : 'эвристика'}
        </span>
      </div>
    </div>
  );
}
