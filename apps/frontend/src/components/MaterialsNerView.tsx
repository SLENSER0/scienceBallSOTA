import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Atom,
  BadgeCheck,
  CircleAlert,
  Layers,
  Loader2,
  Play,
  ScanText,
  Sparkles,
  TrendingUp,
} from 'lucide-react';

// §6.8 — Materials-science domain NER (MatEntityRecognition) fused with GLiNER (§6.7),
// plus MatSciBERT sentence embeddings. Self-contained (no api.ts edits): calls the
// /api/v1/materials-ner router directly with the same session-auth convention as api.ts.

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

interface FusedMention {
  label: string;
  text: string;
  char_start: number;
  char_end: number;
  score: number;
  sources: string[];
  agreement: boolean;
}
interface StatusResponse {
  matscibert_available: boolean;
  matscibert_model: string | null;
  matscibert_hidden: number;
  mat_entity_available: boolean;
  mat_entity_backend: string;
  device: string;
  threshold: number;
  domain_labels: string[];
  materials_labels: string[];
  tag_map: Record<string, string>;
  note: string;
}
interface FuseResponse {
  gliner_backend: string;
  mat_backend: string;
  n_gliner: number;
  n_mat: number;
  n_fused: number;
  n_agreement: number;
  latency_ms: number;
  threshold: number;
  iou_threshold: number;
  mentions: FusedMention[];
}
interface EmbedResponse {
  backend: string;
  model: string | null;
  dim: number;
  n_texts: number;
  latency_ms: number;
  hidden_size: number;
  norms: number[];
}
interface CorpusChunk {
  chunk_id: string;
  page: number | null;
  text: string;
  mentions: FusedMention[];
  n_gliner: number;
  n_mat: number;
  n_fused: number;
  n_agreement: number;
}
interface CorpusResponse {
  gliner_backend: string;
  mat_backend: string;
  threshold: number;
  iou_threshold: number;
  chunks: CorpusChunk[];
  summary: {
    n_chunks: number;
    gliner_mentions: number;
    mat_mentions: number;
    fused_mentions: number;
    agreement: number;
    lift: number;
    lift_pct: number;
    latency_ms: number;
  };
  domain_labels?: string[];
  note?: string;
}

// Stable colour per domain label so highlights read as one system.
const LABEL_HUES: Record<string, string> = {
  material: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  alloy: 'bg-teal-500/20 text-teal-300 border-teal-500/40',
  chemical_element: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
  sample: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  processing_operation: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  equipment: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  property: 'bg-violet-500/20 text-violet-300 border-violet-500/40',
  measurement: 'bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40',
  method: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40',
  application: 'bg-lime-500/20 text-lime-300 border-lime-500/40',
  descriptor: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  lab: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  person: 'bg-pink-500/20 text-pink-300 border-pink-500/40',
  research_team: 'bg-red-500/20 text-red-300 border-red-500/40',
};
function hueFor(label: string): string {
  return LABEL_HUES[label] ?? 'bg-slate-500/20 text-slate-300 border-slate-500/40';
}

const SAMPLE_TEXT =
  'Никелевый сплав ХН77ТЮР подвергали электроэкстракции в католите при температуре 60 °C ' +
  'и плотности тока 250 А/м². Твёрдость образца достигла 320 HV, предел прочности 780 МПа. ' +
  'Фазовый состав Al2O3 и TiO2 определён на дифрактометре в лаборатории материаловедения.';

const EMBED_SAMPLE =
  'Никель;ХН77ТЮР;электроэкстракция;твёрдость 320 HV;предел прочности 780 МПа;Al2O3';

// Render a passage with its fused mentions highlighted inline, using char offsets.
// Agreement (both extractors) is shown with a ring so recall provenance is visible.
function Highlighted({ text, mentions }: { text: string; mentions: FusedMention[] }) {
  const sorted = useMemo(
    () => [...mentions].sort((a, b) => a.char_start - b.char_start),
    [mentions],
  );
  const parts: ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((m, i) => {
    if (m.char_start < cursor) return; // skip overlaps defensively
    if (m.char_start > cursor) parts.push(<span key={`t${i}`}>{text.slice(cursor, m.char_start)}</span>);
    parts.push(
      <span
        key={`m${i}`}
        title={`${m.label} · ${m.score.toFixed(2)} · ${m.sources.join('+')}`}
        className={`rounded border px-1 ${hueFor(m.label)} ${
          m.agreement ? 'ring-1 ring-emerald-400/60' : ''
        }`}
      >
        {text.slice(m.char_start, m.char_end)}
      </span>,
    );
    cursor = m.char_end;
  });
  if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>);
  return <p className="text-sm leading-7 text-ink">{parts}</p>;
}

function BackendPill({ label, backend, real }: { label: string; backend: string; real: boolean }) {
  return (
    <span className="rounded bg-line/40 px-2 py-0.5 text-faint">
      {label}:{' '}
      <span className={`font-mono ${real ? 'text-emerald-300' : 'text-amber-300'}`}>{backend}</span>
    </span>
  );
}

export function MaterialsNerView() {
  const [text, setText] = useState(SAMPLE_TEXT);
  const [embedText, setEmbedText] = useState(EMBED_SAMPLE);
  const [fuseResult, setFuseResult] = useState<FuseResponse | null>(null);
  const [embedResult, setEmbedResult] = useState<EmbedResponse | null>(null);
  const [corpus, setCorpus] = useState<CorpusResponse | null>(null);

  const status = useQuery({
    queryKey: ['materials-ner-status'],
    queryFn: () => apiGet<StatusResponse>('/api/v1/materials-ner/status'),
  });

  const runFuse = useMutation({
    mutationFn: () => apiPost<FuseResponse>('/api/v1/materials-ner/fuse', { text }),
    onSuccess: (d) => setFuseResult(d),
  });
  const runEmbed = useMutation({
    mutationFn: () =>
      apiPost<EmbedResponse>('/api/v1/materials-ner/embed', {
        texts: embedText.split(';').map((s) => s.trim()).filter(Boolean),
      }),
    onSuccess: (d) => setEmbedResult(d),
  });
  const runCorpus = useMutation({
    mutationFn: () => apiGet<CorpusResponse>('/api/v1/materials-ner/corpus?limit=10'),
    onSuccess: (d) => setCorpus(d),
  });

  const live = status.data;
  const matsciReal = !!live?.matscibert_available;
  const anyReal = matsciReal || !!live?.mat_entity_available;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">Материаловедческий NER · §6.8</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          MatSciBERT / MatEntityRecognition + fusion с GLiNER
        </h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Доменный материаловедческий NER (MatEntityRecognition) в fusion с гибким GLiNER (§6.7)
          поднимает recall на материалах, свойствах и процессах сверх любого одиночного экстрактора:
          перекрывающиеся упоминания дедуплицируются по span-IoU, а согласие двух экстракторов
          повышает уверенность. Плюс MatSciBERT-эмбеддинги доменного текста (переиспользуемый
          компонент для индексации и entity resolution). Только OSS-модели; при отсутствии весов —
          честный детерминированный fallback.
        </p>

        {/* Backend status banner */}
        {live && (
          <div
            className={`panel mb-5 flex items-start gap-3 p-4 ${
              anyReal ? 'border-emerald-500/40' : 'border-amber-500/40'
            }`}
          >
            {anyReal ? (
              <BadgeCheck size={26} className="mt-0.5 shrink-0 text-emerald-400" />
            ) : (
              <CircleAlert size={26} className="mt-0.5 shrink-0 text-amber-400" />
            )}
            <div className="min-w-0">
              <div className="font-display text-ink">
                {matsciReal ? (
                  <>
                    Активны реальные MatSciBERT-веса:{' '}
                    <span className="font-mono text-sm text-emerald-300">
                      {live.matscibert_model}
                    </span>{' '}
                    ({live.matscibert_hidden}-dim)
                  </>
                ) : (
                  'MatSciBERT-веса не подключены — hash-fallback той же размерности'
                )}
              </div>
              <div className="mt-1 text-sm text-faint">{live.note}</div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <BackendPill label="matscibert" backend={matsciReal ? 'matscibert' : 'hash-fallback'} real={matsciReal} />
                <BackendPill
                  label="mat-entity"
                  backend={live.mat_entity_backend}
                  real={live.mat_entity_backend === 'mat-entity'}
                />
                <span className="rounded bg-line/40 px-2 py-0.5 text-faint">
                  device: <span className="font-mono text-ink">{live.device}</span>
                </span>
                <span className="rounded bg-line/40 px-2 py-0.5 text-faint">
                  threshold: <span className="font-mono text-ink">{live.threshold}</span>
                </span>
              </div>
            </div>
          </div>
        )}
        {status.isError && (
          <div className="panel mb-5 border-red-500/40 p-3 text-sm text-red-400">
            Статус недоступен: {(status.error as Error).message}
          </div>
        )}

        {/* Tag map (MatEntityRecognition → §8.1) */}
        {live && (
          <div className="panel mb-6 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm text-faint">
              <Layers size={16} className="text-copper" /> Маппинг тегов MatEntityRecognition → §8.1
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(live.tag_map).map(([tag, label]) => (
                <span
                  key={tag}
                  className={`rounded border px-2 py-0.5 text-xs ${hueFor(label)}`}
                >
                  <span className="font-mono">{tag}</span> → {label}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Ad-hoc fusion */}
        <div className="mb-8">
          <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
            <ScanText size={18} className="text-copper" /> Fused-разметка текста (GLiNER ⊕ MatEntity)
          </h3>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            className="mb-3 w-full rounded-lg border border-line bg-panel p-3 text-sm text-ink outline-none focus:border-copper"
            placeholder="Вставьте фрагмент текста для fused NER…"
          />
          <button
            onClick={() => runFuse.mutate()}
            disabled={runFuse.isPending || !text.trim()}
            className="btn-copper flex items-center gap-2"
          >
            {runFuse.isPending ? <Loader2 size={16} className="animate-spin" /> : <Atom size={16} />}
            {runFuse.isPending ? 'Извлечение…' : 'Извлечь и слить сущности'}
          </button>

          {runFuse.isError && (
            <div className="panel mt-3 border-red-500/40 p-3 text-sm text-red-400">
              Ошибка: {(runFuse.error as Error).message}
            </div>
          )}

          {fuseResult && (
            <div className="panel mt-4 p-4">
              <div className="mb-3 grid gap-2 sm:grid-cols-4">
                <div className="rounded bg-line/30 p-2 text-center">
                  <div className="text-xs uppercase text-faint">GLiNER</div>
                  <div className="font-display text-xl text-ink">{fuseResult.n_gliner}</div>
                </div>
                <div className="rounded bg-line/30 p-2 text-center">
                  <div className="text-xs uppercase text-faint">MatEntity</div>
                  <div className="font-display text-xl text-ink">{fuseResult.n_mat}</div>
                </div>
                <div className="rounded bg-line/30 p-2 text-center">
                  <div className="text-xs uppercase text-faint">Fused</div>
                  <div className="font-display text-xl text-emerald-300">{fuseResult.n_fused}</div>
                </div>
                <div className="rounded bg-line/30 p-2 text-center">
                  <div className="text-xs uppercase text-faint">Согласие</div>
                  <div className="font-display text-xl text-copper">{fuseResult.n_agreement}</div>
                </div>
              </div>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-faint">
                <BackendPill label="gliner" backend={fuseResult.gliner_backend} real={fuseResult.gliner_backend === 'gliner'} />
                <BackendPill label="mat" backend={fuseResult.mat_backend} real={fuseResult.mat_backend === 'mat-entity'} />
                <span className="rounded bg-line/40 px-2 py-0.5">
                  IoU: <span className="font-mono text-ink">{fuseResult.iou_threshold}</span>
                </span>
                <span className="rounded bg-line/40 px-2 py-0.5">
                  latency: <span className="font-mono text-ink">{fuseResult.latency_ms} ms</span>
                </span>
              </div>
              <Highlighted text={text} mentions={fuseResult.mentions} />
              <p className="mt-2 text-xs text-faint">
                Обведённые упоминания найдены обоими экстракторами (agreement → выше уверенность).
              </p>
            </div>
          )}
        </div>

        {/* MatSciBERT embeddings */}
        <div className="mb-8">
          <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
            <Sparkles size={18} className="text-copper" /> MatSciBERT-эмбеддинги (батч)
          </h3>
          <p className="mb-3 max-w-3xl text-sm text-faint">
            Доменные векторы для индексации (§9.2 Step 8) и entity resolution. Разделяйте тексты
            символом «;». Возвращаем размерность hidden_size и L2-нормы (нормализованы → ≈ 1.0).
          </p>
          <textarea
            value={embedText}
            onChange={(e) => setEmbedText(e.target.value)}
            rows={2}
            className="mb-3 w-full rounded-lg border border-line bg-panel p-3 text-sm text-ink outline-none focus:border-copper"
          />
          <button
            onClick={() => runEmbed.mutate()}
            disabled={runEmbed.isPending || !embedText.trim()}
            className="btn-copper flex items-center gap-2"
          >
            {runEmbed.isPending ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {runEmbed.isPending ? 'Эмбеддинг…' : 'Построить эмбеддинги'}
          </button>
          {runEmbed.isError && (
            <div className="panel mt-3 border-red-500/40 p-3 text-sm text-red-400">
              Ошибка: {(runEmbed.error as Error).message}
            </div>
          )}
          {embedResult && (
            <div className="panel mt-4 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-faint">
                <BackendPill label="backend" backend={embedResult.backend} real={embedResult.backend === 'matscibert'} />
                <span className="rounded bg-line/40 px-2 py-0.5">
                  dim: <span className="font-mono text-ink">{embedResult.dim}</span>
                </span>
                <span className="rounded bg-line/40 px-2 py-0.5">
                  texts: <span className="font-mono text-ink">{embedResult.n_texts}</span>
                </span>
                <span className="rounded bg-line/40 px-2 py-0.5">
                  latency: <span className="font-mono text-ink">{embedResult.latency_ms} ms</span>
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {embedResult.norms.map((n, i) => (
                  <span key={i} className="rounded bg-line/30 px-2 py-0.5 text-xs font-mono text-ink">
                    ‖v{i}‖ = {n}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Corpus recall lift */}
        <div>
          <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
            <TrendingUp size={18} className="text-copper" /> Recall-подъём fusion на живом корпусе
          </h3>
          <p className="mb-3 max-w-3xl text-sm text-faint">
            Прогон батча реальных чанков из графа: сравниваем fused-стек с GLiNER-базой на одних и
            тех же чанках и показываем, сколько дополнительных упоминаний даёт материаловедческий
            NER в fusion.
          </p>
          <button
            onClick={() => runCorpus.mutate()}
            disabled={runCorpus.isPending}
            className="btn-copper flex items-center gap-2"
          >
            {runCorpus.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {runCorpus.isPending ? 'Прогон корпуса…' : 'Прогнать батч чанков'}
          </button>

          {runCorpus.isError && (
            <div className="panel mt-3 border-red-500/40 p-3 text-sm text-red-400">
              Ошибка: {(runCorpus.error as Error).message}
            </div>
          )}

          {corpus && (
            <div className="mt-4 space-y-4">
              {corpus.note && (
                <div className="panel border-amber-500/40 p-3 text-sm text-amber-300">
                  {corpus.note}
                </div>
              )}
              <div className="grid gap-3 sm:grid-cols-5">
                <div className="panel p-3">
                  <div className="text-xs uppercase text-faint">Чанков</div>
                  <div className="font-display text-2xl text-ink">{corpus.summary.n_chunks}</div>
                </div>
                <div className="panel p-3">
                  <div className="text-xs uppercase text-faint">GLiNER</div>
                  <div className="font-display text-2xl text-ink">
                    {corpus.summary.gliner_mentions}
                  </div>
                </div>
                <div className="panel p-3">
                  <div className="text-xs uppercase text-faint">MatEntity</div>
                  <div className="font-display text-2xl text-ink">
                    {corpus.summary.mat_mentions}
                  </div>
                </div>
                <div className="panel p-3">
                  <div className="text-xs uppercase text-faint">Fused</div>
                  <div className="font-display text-2xl text-emerald-300">
                    {corpus.summary.fused_mentions}
                  </div>
                </div>
                <div className="panel p-3">
                  <div className="text-xs uppercase text-faint">Подъём</div>
                  <div className="font-display text-2xl text-copper">
                    +{corpus.summary.lift}{' '}
                    <span className="text-sm text-faint">({corpus.summary.lift_pct}%)</span>
                  </div>
                </div>
              </div>
              <div className="text-xs text-faint">
                gliner: <span className="font-mono text-ink">{corpus.gliner_backend}</span> · mat:{' '}
                <span className="font-mono text-ink">{corpus.mat_backend}</span> · agreement:{' '}
                <span className="font-mono text-ink">{corpus.summary.agreement}</span> · latency:{' '}
                <span className="font-mono text-ink">{corpus.summary.latency_ms} ms</span>
              </div>

              <div className="space-y-3">
                {corpus.chunks.map((c) => (
                  <div key={c.chunk_id} className="panel p-4">
                    <div className="mb-2 flex items-center gap-2 text-xs text-faint">
                      <span className="font-mono">{c.chunk_id}</span>
                      {c.page != null && <span>· стр. {c.page}</span>}
                      <span className="ml-auto rounded bg-line/40 px-2 py-0.5">
                        G{c.n_gliner} · M{c.n_mat} → {c.n_fused} (agr {c.n_agreement})
                      </span>
                    </div>
                    <Highlighted text={c.text} mentions={c.mentions} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
