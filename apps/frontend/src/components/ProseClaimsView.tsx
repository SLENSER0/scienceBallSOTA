import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  PlayCircle,
  ScrollText,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

// §25.6 prose LLM-claim extraction UI. Self-contained (no api.ts edits): it calls
// the prose-claims router directly with the same session-auth convention as api.ts.

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

interface Priors {
  llm: { recall: number; p_missed: number };
  offline: { recall: number; p_missed: number };
  calibrated: boolean;
}
interface Blindspot {
  material_id: string;
  property_name: string;
  mentions: number;
  documents: string[];
}
interface BlindspotReport {
  blindspots: Blindspot[];
  totals: Record<string, number>;
  error?: string;
}
interface StatusResponse {
  flag_enabled: boolean;
  llm_available: boolean;
  active: boolean;
  flag_attr: string;
  priors: Priors;
  prose_chunks: number;
  blindspot: BlindspotReport | null;
  note: string;
}
interface ChunkRow {
  chunk_id: string;
  doc_id: string;
  text: string;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
}
interface ChunksResponse {
  chunks: ChunkRow[];
  error?: string;
}
interface ClaimProposal {
  material: string | null;
  property: string;
  value: number | null;
  unit: string | null;
  qualifier: string | null;
  evidence: { chunk_id: string; doc_id: string; page: number | null };
  status: string;
  source: string;
}
interface Coverage {
  modality: string;
  seen: number;
  emitted: number;
  property_mentions: number;
}
interface ExtractResponse {
  proposals: ClaimProposal[];
  coverage: Coverage;
  offline: boolean;
  p_missed: number;
  reason: string;
  property_ids: string[];
  input?: { chunk_id: string; doc_id: string; chars: number };
  error?: string;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

export function ProseClaimsView() {
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [forceEnabled, setForceEnabled] = useState<boolean>(false);
  const [result, setResult] = useState<ExtractResponse | null>(null);

  const status = useQuery({
    queryKey: ['prose-claims-status'],
    queryFn: () => apiGet<StatusResponse>('/api/v1/prose-claims/status?blindspot_top=15'),
  });
  const chunks = useQuery({
    queryKey: ['prose-claims-chunks'],
    queryFn: () => apiGet<ChunksResponse>('/api/v1/prose-claims/chunks?limit=25'),
  });

  const run = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<ExtractResponse>('/api/v1/prose-claims/extract', body),
    onSuccess: (d) => setResult(d),
  });

  const st = status.data;
  const chunkList = chunks.data?.chunks ?? [];
  const selectedChunk = chunkList.find((c) => c.chunk_id === selected) ?? null;

  const runExtract = () => {
    const body: Record<string, unknown> = { enabled: forceEnabled ? true : undefined };
    if (selectedChunk) body.chunk_id = selectedChunk.chunk_id;
    else if (text.trim()) {
      body.text = text.trim();
      body.chunk_id = 'adhoc:0';
    } else return;
    run.mutate(body);
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">извлечение из прозы · §25.6</div>
        <h2 className="mb-1 flex items-center gap-2 font-display text-2xl font-semibold">
          <ScrollText className="h-6 w-6 text-accent" /> Факты из прозы (LLM)
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Прозаические чанки давали только coverage-телеметрию и 0 фактов. Governed
          prose-extraction вытаскивает измерения, спрятанные в тексте, как{' '}
          <span className="font-medium">governed proposals</span> (proposal → validate → review) —
          с переиспользованием EvidenceSpan исходного чанка. Без LLM факты не извлекаются, но чанк
          честно логируется как слепая зона с высоким <code>p_missed</code>.
        </p>

        {/* --- Feature state --- */}
        {status.isLoading && (
          <div className="flex items-center gap-2 text-sm text-faint">
            <Loader2 className="h-4 w-4 animate-spin" /> загрузка статуса…
          </div>
        )}
        {st && (
          <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StateCard
              ok={st.flag_enabled}
              title="Feature-flag"
              value={st.flag_enabled ? 'включён' : 'выключен'}
              sub={st.flag_attr}
            />
            <StateCard
              ok={st.llm_available}
              title="LLM"
              value={st.llm_available ? 'доступен' : 'офлайн'}
              sub={st.llm_available ? 'ключ настроен' : 'ключ не настроен'}
            />
            <StateCard
              ok={st.active}
              title="Prose-extraction"
              value={st.active ? 'активна' : 'неактивна'}
              sub={`${st.prose_chunks} prose-чанков`}
            />
          </div>
        )}

        {/* --- Recall priors --- */}
        {st && (
          <div className="mb-6 rounded-lg border border-subtle p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">
              <Sparkles className="h-4 w-4 text-accent" /> Recall-приоры прозы (§25.10, эвристика)
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <PriorBar
                label="С LLM"
                recall={st.priors.llm.recall}
                pMissed={st.priors.llm.p_missed}
                good
              />
              <PriorBar
                label="Офлайн (без LLM)"
                recall={st.priors.offline.recall}
                pMissed={st.priors.offline.p_missed}
              />
            </div>
            <p className="mt-2 text-xs text-faint">
              Офлайн-проза помечается высоким <code>p_missed</code> — absence-layer трактует такой
              пробел как вероятный extraction-miss, а не подлинное отсутствие.
            </p>
          </div>
        )}

        {/* --- Blind spots --- */}
        {st?.blindspot && !st.blindspot.error && (
          <div className="mb-6 rounded-lg border border-subtle p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="h-4 w-4 text-amber-500" /> Слепые зоны — упоминается в прозе,
              но не измерено
            </div>
            <div className="mb-3 flex flex-wrap gap-4 text-xs text-faint">
              <span>ячеек: {st.blindspot.totals.n_blindspots ?? 0}</span>
              <span>материалов: {st.blindspot.totals.n_materials ?? 0}</span>
              <span>свойств: {st.blindspot.totals.n_properties ?? 0}</span>
              <span>упоминаний: {st.blindspot.totals.total_mentions ?? 0}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-faint">
                  <tr>
                    <th className="py-1 pr-4">Материал</th>
                    <th className="py-1 pr-4">Свойство</th>
                    <th className="py-1 pr-4">Упоминаний</th>
                    <th className="py-1">Документы</th>
                  </tr>
                </thead>
                <tbody>
                  {st.blindspot.blindspots.map((b, i) => (
                    <tr key={i} className="border-t border-subtle">
                      <td className="py-1 pr-4 font-mono text-xs">{b.material_id}</td>
                      <td className="py-1 pr-4">{b.property_name}</td>
                      <td className="py-1 pr-4">{b.mentions}</td>
                      <td className="py-1 text-xs text-faint">{b.documents.slice(0, 3).join(', ')}</td>
                    </tr>
                  ))}
                  {st.blindspot.blindspots.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-2 text-xs text-faint">
                        Слепых зон не найдено на текущем графе.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {st?.blindspot?.error && (
          <div className="mb-6 rounded-lg border border-subtle p-3 text-xs text-faint">
            Blind-spot отчёт недоступен: {st.blindspot.error}
          </div>
        )}

        {/* --- Trial panel --- */}
        <div className="rounded-lg border border-subtle p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium">
            <PlayCircle className="h-4 w-4 text-accent" /> Проба извлечения
          </div>

          {chunkList.length > 0 && (
            <div className="mb-3">
              <label className="mb-1 block text-xs uppercase text-faint">
                <FileText className="mr-1 inline h-3 w-3" /> Prose-чанк из графа
              </label>
              <select
                className="w-full rounded border border-subtle bg-transparent px-2 py-1.5 text-sm"
                value={selected ?? ''}
                onChange={(e) => {
                  setSelected(e.target.value || null);
                  setText('');
                }}
              >
                <option value="">— выбрать чанк —</option>
                {chunkList.map((c) => (
                  <option key={c.chunk_id} value={c.chunk_id}>
                    {c.doc_id} · {c.chunk_id} — {c.text.slice(0, 60)}…
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="mb-3">
            <label className="mb-1 block text-xs uppercase text-faint">
              …или ad-hoc текст
            </label>
            <textarea
              className="w-full rounded border border-subtle bg-transparent px-2 py-1.5 text-sm"
              rows={3}
              placeholder="напр.: Микротвёрдость покрытия достигала 320 HV при плотности тока 5 А/дм²."
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setSelected(null);
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <button
              className="btn-primary inline-flex items-center gap-2 text-sm disabled:opacity-50"
              disabled={run.isPending || (!selectedChunk && !text.trim())}
              onClick={runExtract}
            >
              {run.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PlayCircle className="h-4 w-4" />
              )}
              Извлечь факты
            </button>
            <label className="inline-flex items-center gap-2 text-xs text-faint">
              <input
                type="checkbox"
                checked={forceEnabled}
                onChange={(e) => setForceEnabled(e.target.checked)}
              />
              форсировать LLM-ветку (демо, без merge)
            </label>
          </div>

          {run.isError && (
            <div className="mt-3 text-xs text-red-500">{(run.error as Error).message}</div>
          )}

          {result && (
            <div className="mt-4">
              {result.error ? (
                <div className="text-xs text-red-500">{result.error}</div>
              ) : (
                <>
                  <div className="mb-2 flex flex-wrap items-center gap-3 text-xs">
                    <span
                      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 ${
                        result.offline
                          ? 'bg-amber-500/15 text-amber-600'
                          : 'bg-emerald-500/15 text-emerald-600'
                      }`}
                    >
                      {result.offline ? (
                        <AlertTriangle className="h-3 w-3" />
                      ) : (
                        <CheckCircle2 className="h-3 w-3" />
                      )}
                      {result.offline ? 'офлайн — 0 фактов' : `${result.proposals.length} proposals`}
                    </span>
                    <span className="text-faint">
                      coverage: seen {result.coverage.seen} / emitted {result.coverage.emitted} ·
                      упоминаний свойств {result.coverage.property_mentions}
                    </span>
                    <span className="text-faint">p_missed {pct(result.p_missed)}</span>
                    <span className="inline-flex items-center gap-1 text-faint">
                      <ShieldCheck className="h-3 w-3" /> governed
                    </span>
                  </div>
                  <div className="mb-2 text-xs text-faint">{result.reason}</div>
                  {result.proposals.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead className="text-xs uppercase text-faint">
                          <tr>
                            <th className="py-1 pr-4">Материал</th>
                            <th className="py-1 pr-4">Свойство</th>
                            <th className="py-1 pr-4">Значение</th>
                            <th className="py-1 pr-4">Ед.</th>
                            <th className="py-1 pr-4">Условие</th>
                            <th className="py-1 pr-4">Статус</th>
                            <th className="py-1">Evidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.proposals.map((p, i) => (
                            <tr key={i} className="border-t border-subtle">
                              <td className="py-1 pr-4">{p.material ?? '—'}</td>
                              <td className="py-1 pr-4">{p.property}</td>
                              <td className="py-1 pr-4">{p.value ?? '—'}</td>
                              <td className="py-1 pr-4">{p.unit ?? '—'}</td>
                              <td className="py-1 pr-4 text-xs text-faint">{p.qualifier ?? '—'}</td>
                              <td className="py-1 pr-4">
                                <span className="rounded bg-accent/10 px-1.5 py-0.5 text-xs text-accent">
                                  {p.status}
                                </span>
                              </td>
                              <td className="py-1 font-mono text-xs text-faint">
                                {p.evidence.chunk_id}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StateCard({
  ok,
  title,
  value,
  sub,
}: {
  ok: boolean;
  title: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-lg border border-subtle p-3">
      <div className="mb-1 flex items-center justify-between text-xs uppercase text-faint">
        <span>{title}</span>
        <span
          className={`h-2 w-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-zinc-400'}`}
          aria-hidden
        />
      </div>
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-faint">{sub}</div>
    </div>
  );
}

function PriorBar({
  label,
  recall,
  pMissed,
  good,
}: {
  label: string;
  recall: number;
  pMissed: number;
  good?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span>{label}</span>
        <span className="text-faint">
          recall {pct(recall)} · p_missed {pct(pMissed)}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-subtle">
        <div
          className={`h-full ${good ? 'bg-emerald-500' : 'bg-amber-500'}`}
          style={{ width: `${Math.round(recall * 100)}%` }}
        />
      </div>
    </div>
  );
}
