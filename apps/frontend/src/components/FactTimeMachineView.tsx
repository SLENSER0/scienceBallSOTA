import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowRight,
  Clock,
  ExternalLink,
  FileText,
  GitCommitVertical,
  History,
  Loader2,
  Lock,
  PencilLine,
  Quote,
  ScrollText,
  ShieldCheck,
  Unlock,
  UserRound,
  X,
} from 'lucide-react';
import { DocumentViewer } from './DocumentUpload';

// §3.7 «Машина времени факта» + «никогда не перезаписывать reviewed».
// Self-contained (no api.ts edits): вызывает роутер fact-versions напрямую с той
// же session-auth конвенцией, что и api.ts.

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
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = String(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// -- types (mirror fact_versions_store.as_dict) -------------------------------
interface FactVersion {
  version: number;
  value: unknown;
  reviewStatus: string;
  actor: string;
  action: string;
  reason: string;
  decisionId: string | null;
  curationEventId: string | null;
  extractorRunId: string | null;
  schemaVersion: string | null;
  validFrom: string;
  validTo: string | null;
  supersededBy: number | null;
  createdAt: number;
  isCurrent: boolean;
}
interface FactTimeline {
  entityId: string;
  field: string;
  fieldLabel: string;
  versionCount: number;
  reviewed: boolean;
  current: FactVersion;
  versions: FactVersion[];
}
interface FieldSummary {
  field: string;
  fieldLabel: string;
  currentValue: unknown;
  reviewStatus: string;
  versionCount: number;
  reviewed: boolean;
  lastActor: string;
  lastAction: string;
  hasRevisions: boolean;
}
interface EntityFacts {
  entityId: string;
  name: string;
  type: string | null;
  reviewStatus: string | null;
  extractorRunId: string | null;
  schemaVersion: string | null;
  fieldCount: number;
  fields: FieldSummary[];
}
interface NodeRow {
  id: string;
  type?: string;
  name?: string;
}
interface NodesResponse {
  nodes: NodeRow[];
}

// -- provenance / «Источник факта» (GET /fact-versions/{id}/source) -----------
interface EvidenceSrc {
  evidenceId: string;
  text: string;
  page: number | null;
  docId: string | null;
  sourceType: string | null;
  evidenceStrength: string | null;
  confidence: number | null;
}
interface SourceDoc {
  docId: string;
  title: string;
  docType: string;
}
interface FactSource {
  entityId: string;
  evidence: EvidenceSrc[];
  documents: SourceDoc[];
}

const REVIEW_TONE: Record<string, string> = {
  accepted: 'text-emerald-400 bg-emerald-500/15',
  corrected: 'text-sky-400 bg-sky-500/15',
  rejected: 'text-red-400 bg-red-500/15',
  pending: 'text-amber-400 bg-amber-500/15',
};

const ACTION_LABEL: Record<string, string> = {
  extract: 'извлечение',
  correct: 'коррекция',
  accept: 'принятие',
  reject: 'отклонение',
  reopen: 'переоткрытие',
};

function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  return String(v);
}

function fmtDate(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU');
}

function ReviewBadge({ status }: { status: string }) {
  const tone = REVIEW_TONE[status] ?? 'text-faint bg-white/10';
  return <span className={`rounded-full px-2 py-0.5 text-xs ${tone}`}>{status}</span>;
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="panel p-3">
      <div className="text-xs uppercase tracking-wide text-faint">{label}</div>
      <div className="mt-1 font-display text-xl text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-faint">{hint}</div>}
    </div>
  );
}

export function FactTimeMachineView() {
  const qc = useQueryClient();
  const [label, setLabel] = useState('Measurement');
  const [entityId, setEntityId] = useState<string | null>(null);
  const [field, setField] = useState<string | null>(null);
  // Which source document to preview in the modal («Открыть источник»).
  const [openDoc, setOpenDoc] = useState<string | null>(null);

  // Small picker: entities of the chosen type to start from.
  const picker = useQuery({
    queryKey: ['ftm-picker', label],
    queryFn: () =>
      apiGet<NodesResponse>(`/api/v1/graph/nodes?label=${encodeURIComponent(label)}&limit=100`),
  });

  const facts = useQuery({
    queryKey: ['ftm-facts', entityId],
    queryFn: () => apiGet<EntityFacts>(`/api/v1/fact-versions/${encodeURIComponent(entityId!)}`),
    enabled: !!entityId,
  });

  const timeline = useQuery({
    queryKey: ['ftm-timeline', entityId, field],
    queryFn: () =>
      apiGet<FactTimeline>(
        `/api/v1/fact-versions/${encodeURIComponent(entityId!)}/${encodeURIComponent(field!)}`,
      ),
    enabled: !!entityId && !!field,
  });

  // Provenance for the whole selected entity/fact: which document(s) it was
  // extracted from + the evidence quotes. Per-fact, so keyed on entityId only.
  const source = useQuery({
    queryKey: ['ftm-source', entityId],
    queryFn: () =>
      apiGet<FactSource>(`/api/v1/fact-versions/${encodeURIComponent(entityId!)}/source`),
    enabled: !!entityId,
  });

  function loadEntity(id: string) {
    const trimmed = id.trim();
    if (!trimmed) return;
    setEntityId(trimmed);
    setField(null);
  }

  const selectedField = useMemo(
    () => facts.data?.fields.find((f) => f.field === field) ?? null,
    [facts.data, field],
  );

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="eyebrow mb-1">история изменений факта</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">Версионирование фактов</h2>
        <p className="mb-5 max-w-3xl text-sm text-faint">
          Как менялось каждое число: первая версия — из исходного документа, а каждая
          правка эксперта создаёт <b>новую версию</b> со ссылкой на обоснование — не
          перезаписывая предыдущую. Проверенные значения защищены от автоматической
          перезаписи: изменить их можно только вручную, с указанием причины.
        </p>

        {/* Entity picker */}
        <div className="panel mb-5 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[180px]">
              <label className="mb-1 block text-xs uppercase tracking-wide text-faint">
                Тип сущности
              </label>
              <select
                value={label}
                onChange={(e) => {
                  // Switching type invalidates the current pick — clear it so the
                  // fields/timeline below don't keep showing the old-type entity.
                  setLabel(e.target.value);
                  setEntityId(null);
                  setField(null);
                }}
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
              >
                <option value="Measurement">Измерение</option>
                <option value="Material">Материал</option>
                <option value="Composition">Состав</option>
                <option value="Solution">Решение</option>
              </select>
            </div>
            <div className="flex-1 min-w-[240px]">
              <label className="mb-1 block text-xs uppercase tracking-wide text-faint">
                Идентификатор сущности
              </label>
              {picker.isLoading ? (
                <select
                  disabled
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50 disabled:opacity-60"
                >
                  <option>загрузка…</option>
                </select>
              ) : picker.data && picker.data.nodes.length > 0 ? (
                <select
                  value={entityId ?? ''}
                  onChange={(e) => loadEntity(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
                >
                  <option value="" disabled>
                    — выберите сущность —
                  </option>
                  {picker.data.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name || n.id}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  disabled
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50 disabled:opacity-60"
                >
                  <option>нет сущностей этого типа</option>
                </select>
              )}
            </div>
          </div>
        </div>

        {facts.isLoading && (
          <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
            <Loader2 size={16} className="animate-spin" /> Загрузка полей сущности…
          </div>
        )}
        {facts.isError && (
          <div className="panel mb-4 border-red-500/40 p-3 text-sm text-red-400">
            Ошибка: {(facts.error as Error).message}
          </div>
        )}

        {facts.data && (
          <>
            <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label="Сущность" value={facts.data.name} hint={facts.data.type ?? ''} />
              <StatTile label="Версионируемых полей" value={String(facts.data.fieldCount)} />
              <StatTile
                label="Статус ревью"
                value={facts.data.reviewStatus ?? '—'}
                hint="по всей сущности"
              />
              <StatTile
                label="Происхождение"
                value={facts.data.extractorRunId ? '✓' : '—'}
                hint={facts.data.schemaVersion ? `версия данных ${facts.data.schemaVersion}` : ''}
              />
            </div>

            {/* «Источник факта» — откуда взят факт: документ(ы) + цитаты-обоснования */}
            <FactSourcePanel
              data={source.data}
              isLoading={source.isLoading}
              onOpenDoc={setOpenDoc}
            />

            <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_1fr]">
              {/* fields list */}
              <div className="panel p-3">
                <div className="mb-2 flex items-center gap-2 text-sm text-faint">
                  <ScrollText size={15} className="text-copper" /> Поля-факты
                </div>
                <div className="flex flex-col gap-1">
                  {facts.data.fields.map((f) => (
                    <button
                      key={f.field}
                      onClick={() => setField(f.field)}
                      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${
                        field === f.field
                          ? 'border-copper/50 bg-copper/10'
                          : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05]'
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="truncate text-ink">{f.fieldLabel}</div>
                        <div className="truncate text-xs text-faint">
                          {fmtValue(f.currentValue)}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        {f.reviewed ? (
                          <Lock size={13} className="text-emerald-400" />
                        ) : (
                          <Unlock size={13} className="text-faint" />
                        )}
                        {f.versionCount > 1 && (
                          <span className="rounded-full bg-copper/15 px-1.5 py-0.5 text-[10px] text-copper">
                            v{f.versionCount}
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* timeline + revise */}
              <div className="min-w-0">
                {!field && (
                  <div className="panel flex items-center gap-2 p-6 text-sm text-faint">
                    <History size={16} /> Выберите поле слева, чтобы увидеть его ленту версий.
                  </div>
                )}
                {field && timeline.isLoading && (
                  <div className="panel flex items-center gap-2 p-4 text-sm text-faint">
                    <Loader2 size={16} className="animate-spin" /> Загрузка ленты версий…
                  </div>
                )}
                {field && timeline.data && (
                  <TimelinePanel
                    tl={timeline.data}
                    fieldSummary={selectedField}
                    onRevised={() => {
                      qc.invalidateQueries({ queryKey: ['ftm-timeline', entityId, field] });
                      qc.invalidateQueries({ queryKey: ['ftm-facts', entityId] });
                    }}
                  />
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Full source document preview (reuses the DocumentUpload viewer). */}
      {openDoc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/70 p-4"
          onClick={() => setOpenDoc(null)}
        >
          <div className="panel w-full max-w-3xl p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-nickel">
                <FileText size={15} className="text-copper" /> Источник факта
              </div>
              <button
                onClick={() => setOpenDoc(null)}
                className="rounded p-1 text-faint hover:text-copper"
                title="Закрыть"
              >
                <X size={16} />
              </button>
            </div>
            <DocumentViewer docId={openDoc} />
          </div>
        </div>
      )}
    </div>
  );
}

function FactSourcePanel({
  data,
  isLoading,
  onOpenDoc,
}: {
  data: FactSource | undefined;
  isLoading: boolean;
  onOpenDoc: (docId: string) => void;
}) {
  return (
    <div className="panel mb-5 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-faint">
        <FileText size={15} className="text-copper" /> Источник факта
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-faint">
          <Loader2 size={16} className="animate-spin" /> Загрузка источника…
        </div>
      ) : !data || (data.documents.length === 0 && data.evidence.length === 0) ? (
        <div className="text-sm text-faint">
          У этого факта нет привязанного источника в графе (например, посевные значения).
        </div>
      ) : data.documents.length === 0 ? (
        // Evidence есть, но документ не сматчился — показываем цитаты без группировки.
        <div className="flex flex-col gap-2">
          <div className="text-xs text-faint">Цитаты-источники (документ не сопоставлен в графе):</div>
          {data.evidence.map((e) => (
            <blockquote
              key={e.evidenceId}
              className="rounded-r border-l-2 border-copper/40 bg-white/[0.02] py-1.5 pl-3 pr-2 text-xs text-faint"
            >
              <div className="flex gap-1.5">
                <Quote size={12} className="mt-0.5 shrink-0 text-copper/70" />
                <span className="line-clamp-3 italic">{e.text}</span>
              </div>
              {(e.page != null || e.evidenceStrength) && (
                <div className="mt-1 flex flex-wrap items-center gap-2 pl-[18px] text-[11px] text-faint/80">
                  {e.page != null && <span>стр. {e.page}</span>}
                  {e.evidenceStrength && (
                    <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-copper">
                      {e.evidenceStrength}
                    </span>
                  )}
                </div>
              )}
            </blockquote>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {data.documents.map((doc) => {
            const quotes = data.evidence.filter((e) => e.docId === doc.docId);
            const chip =
              doc.docType === 'paper'
                ? 'bg-sky-500/15 text-sky-400'
                : 'bg-white/10 text-faint';
            return (
              <div
                key={doc.docId}
                className="rounded-lg border border-white/10 bg-white/[0.02] p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    <ScrollText size={15} className="mt-0.5 shrink-0 text-copper" />
                    <div className="min-w-0 text-sm text-ink">{doc.title}</div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${chip}`}>
                      {doc.docType}
                    </span>
                  </div>
                  <button
                    onClick={() => onOpenDoc(doc.docId)}
                    className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-copper/20 px-3 py-1.5 text-sm text-copper hover:bg-copper/30"
                  >
                    <ExternalLink size={14} /> Открыть источник
                  </button>
                </div>

                {quotes.length > 0 && (
                  <div className="mt-2 flex flex-col gap-2">
                    {quotes.map((e) => (
                      <blockquote
                        key={e.evidenceId}
                        className="rounded-r border-l-2 border-copper/40 bg-white/[0.02] py-1.5 pl-3 pr-2 text-xs text-faint"
                      >
                        <div className="flex gap-1.5">
                          <Quote size={12} className="mt-0.5 shrink-0 text-copper/70" />
                          <span className="line-clamp-3 italic">{e.text}</span>
                        </div>
                        {(e.page != null || e.evidenceStrength) && (
                          <div className="mt-1 flex flex-wrap items-center gap-2 pl-[18px] text-[11px] text-faint/80">
                            {e.page != null && <span>стр. {e.page}</span>}
                            {e.evidenceStrength && (
                              <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-copper">
                                {e.evidenceStrength}
                              </span>
                            )}
                          </div>
                        )}
                      </blockquote>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TimelinePanel({
  tl,
  fieldSummary,
  onRevised,
}: {
  tl: FactTimeline;
  fieldSummary: FieldSummary | null;
  onRevised: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [action, setAction] = useState('correct');
  const [reason, setReason] = useState('');
  const [ceId, setCeId] = useState('');
  const reviewed = tl.reviewed;

  const revise = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/fact-versions/${encodeURIComponent(tl.entityId)}/${encodeURIComponent(tl.field)}/revise`, {
        value: coerce(value, tl.current.value),
        action,
        reason,
        curation_event_id: ceId || null,
        force_curation: reviewed,
      }),
    onSuccess: () => {
      setOpen(false);
      setValue('');
      setReason('');
      setCeId('');
      onRevised();
    },
  });

  const versionsDesc = [...tl.versions].reverse();

  return (
    <div className="flex flex-col gap-4">
      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GitCommitVertical size={18} className="text-copper" />
            <h3 className="font-display text-lg">{tl.fieldLabel}</h3>
            {reviewed ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400">
                <ShieldCheck size={12} /> проверено — защищено
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-0.5 text-xs text-faint">
                <Unlock size={12} /> можно править
              </span>
            )}
          </div>
          <button
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 rounded-lg bg-copper/20 px-3 py-1.5 text-sm text-copper hover:bg-copper/30"
          >
            <PencilLine size={14} /> Новая версия
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2 text-sm text-faint">
          Текущее значение:
          <span className="font-mono text-ink">{fmtValue(tl.current.value)}</span>
          <ReviewBadge status={tl.current.reviewStatus} />
          <span className="text-xs">· {tl.versionCount} версий</span>
        </div>

        {open && (
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.02] p-3">
            {reviewed && (
              <div className="mb-2 flex items-start gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                Значение проверено экспертом. Изменить его можно только вручную — укажите
                основание, оно будет зафиксировано в решении.
              </div>
            )}
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="text-xs text-faint">
                Новое значение
                <input
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder={fmtValue(tl.current.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
                />
              </label>
              <label className="text-xs text-faint">
                Действие
                <select
                  value={action}
                  onChange={(e) => setAction(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
                >
                  <option value="correct">Коррекция</option>
                  <option value="accept">Принять</option>
                  <option value="reject">Отклонить</option>
                  <option value="reopen">Переоткрыть</option>
                </select>
              </label>
              <label className="text-xs text-faint sm:col-span-2">
                Причина
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="почему меняем значение"
                  className="mt-1 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
                />
              </label>
              {reviewed && (
                <label className="text-xs text-faint sm:col-span-2">
                  Основание правки (обязательно для проверенного значения)
                  <input
                    value={ceId}
                    onChange={(e) => setCeId(e.target.value)}
                    placeholder="ce:..."
                    className="mt-1 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-ink outline-none focus:border-copper/50"
                  />
                </label>
              )}
            </div>
            {revise.isError && (
              <div className="mt-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
                {(revise.error as Error).message}
              </div>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-1.5 text-sm text-faint hover:text-ink"
              >
                Отмена
              </button>
              <button
                disabled={revise.isPending || (reviewed && !ceId)}
                onClick={() => revise.mutate()}
                className="inline-flex items-center gap-1 rounded-lg bg-copper/20 px-3 py-1.5 text-sm text-copper hover:bg-copper/30 disabled:opacity-40"
              >
                {revise.isPending && <Loader2 size={14} className="animate-spin" />} Сохранить версию
              </button>
            </div>
          </div>
        )}
      </div>

      {/* version chain */}
      <div className="panel p-4">
        <div className="mb-3 flex items-center gap-2 text-sm text-faint">
          <Clock size={15} className="text-copper" /> Лента версий (новые сверху)
        </div>
        <ol className="relative ml-2 border-l border-white/10">
          {versionsDesc.map((v) => (
            <li key={v.version} className="mb-4 ml-4">
              <span
                className={`absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full ${
                  v.isCurrent ? 'bg-copper' : 'bg-white/20'
                }`}
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm text-ink">v{v.version}</span>
                <span className="font-mono text-base text-ink">{fmtValue(v.value)}</span>
                <ReviewBadge status={v.reviewStatus} />
                {v.isCurrent && (
                  <span className="rounded-full bg-copper/15 px-2 py-0.5 text-[10px] text-copper">
                    текущая
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-faint">
                <span className="inline-flex items-center gap-1">
                  <UserRound size={12} /> {v.actor}
                </span>
                <span>{ACTION_LABEL[v.action] ?? v.action}</span>
                <span>{fmtDate(v.validFrom)}</span>
                {v.validTo && (
                  <span className="inline-flex items-center gap-1 text-faint/70">
                    <ArrowRight size={11} /> закрыта {fmtDate(v.validTo)}
                  </span>
                )}
              </div>
              {v.reason && <div className="mt-1 text-xs text-faint italic">«{v.reason}»</div>}
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-faint/80">
                {v.decisionId && (
                  <span className="inline-flex items-center gap-1">
                    <ScrollText size={10} /> решение {v.decisionId}
                  </span>
                )}
                {v.curationEventId && <span>событие {v.curationEventId}</span>}
                {v.extractorRunId && <span>извлечение {v.extractorRunId}</span>}
                {v.supersededBy && <span>→ заменена версией v{v.supersededBy}</span>}
              </div>
            </li>
          ))}
        </ol>
      </div>

      {fieldSummary && fieldSummary.hasRevisions && (
        <div className="text-xs text-faint">
          Последнее изменение: {fieldSummary.lastActor} · {ACTION_LABEL[fieldSummary.lastAction] ?? fieldSummary.lastAction}
        </div>
      )}
    </div>
  );
}

function coerce(raw: string, prev: unknown): unknown {
  const t = raw.trim();
  if (t === '') return prev;
  if (typeof prev === 'number' || /^-?\d+(\.\d+)?$/.test(t)) {
    const n = Number(t);
    if (!Number.isNaN(n)) return n;
  }
  return t;
}
