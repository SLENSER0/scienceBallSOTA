import { useState } from 'react';
import {
  Beaker,
  BadgeCheck,
  Clock,
  Cpu,
  FlaskConical,
  Loader2,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react';
import { useStore } from '../store';

// §10.10 Provenance-контекст агента в citations: owner/lab/version/freshness.
// The chat/answer surface already renders geo · year · date-of-actualization on
// each citation; this view completes that into a FULL provenance block — owner,
// lab, catalog version, freshness verdict, extractor/model and review_status —
// by running a question, taking its citations and enriching them through the
// /api/v1/citation-provenance/enrich endpoint (pure kg_common provenance engine).

interface FreshnessDetail {
  source_id: string;
  last_ingest_at: string | null;
  age_days: number | null;
  level: string;
}
interface Provenance {
  doc_id: string;
  owner?: string;
  lab?: string;
  version?: string;
  freshness?: string;
  extractor?: string;
  model?: string;
  review_status?: string;
  freshness_detail?: FreshnessDetail;
}
interface EnrichedCitation {
  doc_id: string;
  marker?: string;
  provenance: Provenance;
}
interface EnrichSummary {
  total: number;
  resolved: number;
  missing: number;
  coverage: Record<string, number>;
  fresh: number;
  aging: number;
  stale: number;
  unknown: number;
}
interface EnrichResponse {
  as_of: string;
  citations: EnrichedCitation[];
  missing_provenance: string[];
  summary: EnrichSummary;
}

// Minimal shapes of the /api/v1/query answer we consume (camelCase from gateway).
interface QueryEvidence {
  evidenceId?: string;
  sourceId?: string;
  docId?: string | null;
}
interface QueryCitation {
  marker: string;
  evidence?: QueryEvidence;
  sourceTitle?: string | null;
  year?: number | null;
  geography?: string | null;
  asOf?: string | null;
}
interface QueryAnswer {
  citations: QueryCitation[];
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

const FRESH_STYLE: Record<string, string> = {
  fresh: 'border-verified/40 bg-verified/10 text-verified',
  aging: 'border-gap/40 bg-gap/10 text-gap',
  stale: 'border-contradiction/40 bg-contradiction/10 text-contradiction',
  unknown: 'border-line bg-surface/40 text-muted',
};
const FRESH_LABEL: Record<string, string> = {
  fresh: 'свежий',
  aging: 'стареющий',
  stale: 'устаревший',
  unknown: 'нет даты',
};

async function json<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

function ProvChip({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof User;
  label: string;
  value?: string;
}) {
  if (!value) return null;
  return (
    <span className="chip flex items-center gap-1 border-line text-nickel" title={label}>
      <Icon size={12} className="text-faint" />
      {value}
    </span>
  );
}

export function ProvenanceCitationsView() {
  const { role, useLlm } = useStore();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<EnrichResponse | null>(null);

  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const answer = await json<QueryAnswer>('/api/v1/query', {
        query: q.trim(),
        role,
        use_llm: useLlm,
        geography: null,
      });
      const citations = (answer.citations ?? []).map((c) => ({
        doc_id: c.evidence?.docId ?? c.evidence?.sourceId ?? '',
        source_id: c.evidence?.sourceId ?? null,
        evidence_id: c.evidence?.evidenceId ?? null,
        marker: c.marker,
      }));
      if (citations.length === 0) {
        setData({
          as_of: new Date().toISOString(),
          citations: [],
          missing_provenance: [],
          summary: {
            total: 0,
            resolved: 0,
            missing: 0,
            coverage: {},
            fresh: 0,
            aging: 0,
            stale: 0,
            unknown: 0,
          },
        });
        return;
      }
      const enriched = await json<EnrichResponse>('/api/v1/citation-provenance/enrich', {
        citations,
      });
      setData(enriched);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const loadDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/citation-provenance/demo', { headers: authHeaders() });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setData((await res.json()) as EnrichResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const s = data?.summary;

  return (
    <div className="mx-auto max-w-4xl px-6 py-6">
      <div className="mb-1 flex items-center gap-2">
        <ShieldCheck size={18} className="text-copper" />
        <h1 className="text-lg font-semibold text-ink">Провенанс цитат</h1>
      </div>
      <p className="mb-5 text-sm text-muted">
        Каждая цитата ответа уже несёт гео · год · дату актуализации. Здесь провенанс достроен до
        полного: <span className="text-nickel">владелец · лаборатория · версия · свежесть</span>,
        а также извлекатель/модель и статус курирования — из каталога/графа. Прямой прирост
        доверия к ответу.
      </p>

      <textarea
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Вопрос по материалу/процессу — например «выщелачивание меди в кислой среде»…"
        rows={3}
        className="w-full resize-y rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
      />

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => void run()}
          disabled={!q.trim() || busy}
          className="chip flex items-center gap-1.5 border-copper/40 text-copper hover:bg-copper/10 disabled:opacity-40"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          Спросить и раскрыть провенанс
        </button>
        <button
          onClick={() => void loadDemo()}
          disabled={busy}
          className="chip flex items-center gap-1.5 border-line text-nickel hover:border-copper/40 hover:text-copper disabled:opacity-40"
          title="Показать полный провенанс на демо-данных (§10.10)"
        >
          <Beaker size={13} /> Демо
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-contradiction/40 bg-contradiction/10 px-3 py-2 text-sm text-contradiction">
          Ошибка: {error}
        </div>
      )}

      {s && (
        <div className="mt-6 flex flex-wrap items-center gap-2 text-xs">
          <span className="eyebrow">итог</span>
          <span className="chip text-nickel">
            цитат: {s.resolved}/{s.total}
          </span>
          <span className="chip text-verified">свежих: {s.fresh}</span>
          <span className="chip text-gap">стареющих: {s.aging}</span>
          <span className="chip text-contradiction">устаревших: {s.stale}</span>
          {s.unknown > 0 && <span className="chip text-muted">без даты: {s.unknown}</span>}
          {s.missing > 0 && (
            <span className="chip text-muted" title="Цитаты без узла источника в графе">
              не найдено: {s.missing}
            </span>
          )}
        </div>
      )}

      {data && data.citations.length === 0 && !error && (
        <div className="mt-6 rounded-md border border-line bg-surface/40 px-3 py-4 text-sm text-muted">
          Ответ не вернул цитат для этого вопроса — попробуйте другой запрос или «Демо».
        </div>
      )}

      <div className="mt-4 space-y-3">
        {data?.citations.map((c) => {
          const p = c.provenance ?? { doc_id: c.doc_id };
          const level = p.freshness ?? 'unknown';
          const fd = p.freshness_detail;
          return (
            <div
              key={`${c.marker ?? ''}-${c.doc_id}`}
              className="rounded-md border border-line bg-surface/40 p-4"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                {c.marker && (
                  <span className="metric font-mono text-xs text-copper">{c.marker}</span>
                )}
                <span className="break-all font-mono text-xs text-nickel">{p.doc_id}</span>
                <span
                  className={`chip flex items-center gap-1 ${FRESH_STYLE[level] ?? FRESH_STYLE.unknown}`}
                  title={
                    fd?.last_ingest_at
                      ? `актуализация: ${fd.last_ingest_at.slice(0, 10)}${
                          fd.age_days != null ? ` · ${fd.age_days} дн.` : ''
                        }`
                      : 'нет даты актуализации'
                  }
                >
                  <Clock size={12} />
                  {FRESH_LABEL[level] ?? level}
                  {fd?.age_days != null ? ` · ${fd.age_days}д` : ''}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <ProvChip icon={User} label="владелец" value={p.owner} />
                <ProvChip icon={FlaskConical} label="лаборатория" value={p.lab} />
                <ProvChip icon={BadgeCheck} label="версия каталога" value={p.version && `v${p.version}`} />
                <ProvChip icon={Cpu} label="извлекатель" value={p.extractor} />
                <ProvChip icon={Cpu} label="модель" value={p.model} />
                <ProvChip icon={Beaker} label="статус курирования" value={p.review_status} />
              </div>
              {!p.owner && !p.lab && !p.version && !p.extractor && !p.model && (
                <p className="mt-2 text-xs text-faint">
                  В графе для этого источника нет метаданных владельца/лаборатории — показана только
                  свежесть.
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
