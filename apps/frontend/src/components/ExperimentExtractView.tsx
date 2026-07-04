import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  FlaskConical,
  Loader2,
  Microscope,
  Quote,
  RefreshCw,
  Wrench,
} from 'lucide-react';
import { api } from '../api';

// Панель §6.9 — «Полный ExperimentExtract».
// Прогоняет LLM schema-guided extraction на прозаическом чанке (или произвольном
// тексте) и показывает: (1) полный ExperimentExtract (материалы, режимы,
// измерения, оборудование, лаборатории); (2) разделение claims[] на Claim vs
// Finding с правило-перекрёстной проверкой; (3) прозрачный retry/repair-трейс
// невалидного JSON (сколько попыток, был ли repair, сколько фактов отброшено).
// Только чтение — ничего в граф не пишется.

type ExtractChunk = { chunk_id: string; doc_id: string; text: string; page: number | null };

type ClaimFinding = {
  statement: string;
  claim_type: 'claim' | 'finding';
  about_material: string | null;
  about_property: string | null;
  about_regime: string | null;
  evidence_text: string;
  confidence: number;
  fine_class: string | null;
  rule_agrees: boolean | null;
};

type Regime = {
  operation: string;
  temperature_c: number | null;
  time_h: number | null;
  atmosphere: string | null;
  evidence_text: string;
  confidence: number;
};

type Measurement = {
  material: string | null;
  property: string;
  value: number | null;
  unit: string | null;
  condition: string | null;
  effect_direction: string | null;
  evidence_text: string;
  confidence: number;
};

type ExtractResult = {
  error?: string;
  llm_available?: boolean;
  extract?: {
    title: string | null;
    material_mentions: string[];
    processing: Regime[];
    measurements: Measurement[];
    equipment_mentions: string[];
    lab_mentions: string[];
    claims: ClaimFinding[];
  };
  counts?: Record<string, number>;
  repair?: {
    attempts: number;
    repaired: boolean;
    dropped: number;
    dropped_reasons: string[];
    errors: string[];
    dropped_all: boolean;
  };
  input?: { chunk_id: string; doc_id: string; chars: number };
};

const CARD =
  'rounded-xl border border-stone-200 bg-white dark:border-stone-700 dark:bg-stone-900';

function pct(x: number): string {
  return `${Math.round((x ?? 0) * 100)}%`;
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-2 py-0.5 text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-300">
      <span className="font-medium text-stone-500 dark:text-stone-400">{label}</span>
      {value}
    </span>
  );
}

export function ExperimentExtractView() {
  const [text, setText] = useState('');
  const [selectedChunk, setSelectedChunk] = useState<string | null>(null);

  const status = useQuery({
    queryKey: ['experiment-extract-status'],
    queryFn: () => api.experimentExtractStatus(),
    staleTime: 60_000,
  });

  const chunks = useQuery({
    queryKey: ['experiment-extract-chunks'],
    queryFn: () => api.experimentExtractChunks(30),
    staleTime: 60_000,
  });

  const run = useMutation({
    mutationFn: (payload: { chunk_id?: string; text?: string }) =>
      api.experimentExtractRun(payload),
  });

  const result = run.data as ExtractResult | undefined;
  const ex = result?.extract;
  const repair = result?.repair;

  const findings = useMemo(
    () => (ex?.claims ?? []).filter((c) => c.claim_type === 'finding'),
    [ex],
  );
  const assertions = useMemo(
    () => (ex?.claims ?? []).filter((c) => c.claim_type === 'claim'),
    [ex],
  );

  const llmOn = status.data?.llm_available ?? true;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800 dark:text-stone-100">
            <FlaskConical className="h-5 w-5 text-amber-600" />
            Полный ExperimentExtract
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-stone-500 dark:text-stone-400">
            §6.9 — schema-guided LLM-извлечение эксперимента с разделением Claim vs
            Finding и прозрачным retry/repair невалидного JSON. Только чтение — граф
            не изменяется.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
          {llmOn ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
              <CheckCircle2 className="h-3.5 w-3.5" /> LLM доступен
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5" /> LLM недоступен
            </span>
          )}
          {status.data?.model && <Chip label="model" value={status.data.model} />}
          {status.data?.prose_chunks != null && (
            <Chip label="прозы" value={String(status.data.prose_chunks)} />
          )}
        </div>
      </header>

      {/* Input */}
      <div className={`${CARD} p-4`}>
        <label className="mb-1 block text-xs font-medium text-stone-500 dark:text-stone-400">
          Текст фрагмента
        </label>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setSelectedChunk(null);
          }}
          rows={4}
          placeholder="Вставьте абзац из документа (режимы обработки, измерения, выводы)…"
          className="w-full resize-y rounded-lg border border-stone-300 bg-stone-50 px-3 py-2 text-sm text-stone-800 outline-none focus:border-amber-500 dark:border-stone-600 dark:bg-stone-950 dark:text-stone-100"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            disabled={run.isPending || (!text.trim() && !selectedChunk)}
            onClick={() =>
              run.mutate(
                selectedChunk ? { chunk_id: selectedChunk } : { text: text.trim() },
              )
            }
            className="inline-flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {run.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Beaker className="h-4 w-4" />
            )}
            Извлечь эксперимент
          </button>
          {selectedChunk && (
            <span className="text-xs text-stone-500 dark:text-stone-400">
              чанк: <code className="text-amber-600">{selectedChunk}</code>
            </span>
          )}
        </div>

        {/* Sample chunks */}
        {(chunks.data?.chunks?.length ?? 0) > 0 && (
          <div className="mt-3 border-t border-stone-100 pt-3 dark:border-stone-800">
            <div className="mb-1 text-xs font-medium text-stone-500 dark:text-stone-400">
              …или выберите прозаический чанк из графа:
            </div>
            <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
              {(chunks.data?.chunks ?? []).map((c: ExtractChunk) => (
                <button
                  key={c.chunk_id}
                  onClick={() => {
                    setSelectedChunk(c.chunk_id);
                    setText(c.text.slice(0, 1200));
                  }}
                  className={`max-w-[280px] truncate rounded-md border px-2 py-1 text-left text-xs ${
                    selectedChunk === c.chunk_id
                      ? 'border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200'
                      : 'border-stone-200 text-stone-600 hover:border-amber-300 dark:border-stone-700 dark:text-stone-300'
                  }`}
                  title={c.text}
                >
                  {c.text.slice(0, 60)}…
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {run.isError && (
        <div className={`${CARD} border-red-300 p-3 text-sm text-red-600 dark:text-red-400`}>
          Ошибка запроса: {(run.error as Error)?.message}
        </div>
      )}

      {result?.error && (
        <div className={`${CARD} border-amber-300 p-3 text-sm text-amber-700 dark:text-amber-300`}>
          {result.error}
        </div>
      )}

      {/* Repair / retry trace */}
      {repair && (
        <div className={`${CARD} p-4`}>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
            <RefreshCw className="h-4 w-4 text-blue-600" /> Retry / repair-трейс
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Chip label="попыток" value={String(repair.attempts)} />
            <span
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 ${
                repair.repaired
                  ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300'
                  : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
              }`}
            >
              {repair.repaired ? 'потребовался repair' : 'с первой попытки'}
            </span>
            {repair.dropped > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                отброшено фактов без span: {repair.dropped}
              </span>
            )}
            {repair.dropped_all && (
              <span className="inline-flex items-center gap-1 rounded-md bg-red-50 px-2 py-0.5 text-red-700 dark:bg-red-950 dark:text-red-300">
                <AlertTriangle className="h-3.5 w-3.5" /> controlled drop (бюджет исчерпан)
              </span>
            )}
          </div>
          {repair.dropped_reasons.length > 0 && (
            <ul className="mt-2 list-inside list-disc text-xs text-stone-500 dark:text-stone-400">
              {repair.dropped_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
          {repair.errors.length > 0 && (
            <details className="mt-2 text-xs text-stone-500 dark:text-stone-400">
              <summary className="cursor-pointer">ошибки парсинга/валидации ({repair.errors.length})</summary>
              <ul className="mt-1 list-inside list-disc">
                {repair.errors.map((e, i) => (
                  <li key={i} className="break-words">
                    {e}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Extract body */}
      {ex && !result?.error && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Claims: split Claim vs Finding */}
          <div className={`${CARD} p-4 lg:col-span-2`}>
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
              <Quote className="h-4 w-4 text-purple-600" /> Утверждения — Claim vs Finding (§8.1)
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <ClaimColumn
                title="Findings — эмпирические результаты"
                accent="emerald"
                claims={findings}
              />
              <ClaimColumn
                title="Claims — утверждения / рекомендации"
                accent="amber"
                claims={assertions}
              />
            </div>
          </div>

          {/* Measurements */}
          <div className={`${CARD} p-4`}>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
              <Microscope className="h-4 w-4 text-teal-600" /> Измерения ({ex.measurements.length})
            </div>
            {ex.measurements.length === 0 ? (
              <p className="text-xs text-stone-400">нет</p>
            ) : (
              <div className="flex flex-col gap-2">
                {ex.measurements.map((m, i) => (
                  <div key={i} className="rounded-lg bg-stone-50 p-2 dark:bg-stone-800">
                    <div className="text-sm text-stone-800 dark:text-stone-100">
                      <span className="font-medium">{m.property}</span>{' '}
                      {m.value != null && (
                        <span className="text-teal-700 dark:text-teal-300">
                          {m.value} {m.unit ?? ''}
                        </span>
                      )}
                      {m.material && (
                        <span className="text-stone-500 dark:text-stone-400"> · {m.material}</span>
                      )}
                    </div>
                    {m.effect_direction && (
                      <Chip label="эффект" value={m.effect_direction} />
                    )}
                    <EvidenceLine text={m.evidence_text} conf={m.confidence} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Regimes */}
          <div className={`${CARD} p-4`}>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
              <Wrench className="h-4 w-4 text-orange-600" /> Режимы обработки ({ex.processing.length})
            </div>
            {ex.processing.length === 0 ? (
              <p className="text-xs text-stone-400">нет</p>
            ) : (
              <div className="flex flex-col gap-2">
                {ex.processing.map((r, i) => (
                  <div key={i} className="rounded-lg bg-stone-50 p-2 dark:bg-stone-800">
                    <div className="text-sm font-medium text-stone-800 dark:text-stone-100">
                      {r.operation}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {r.temperature_c != null && (
                        <Chip label="T" value={`${r.temperature_c} °C`} />
                      )}
                      {r.time_h != null && <Chip label="t" value={`${r.time_h} ч`} />}
                      {r.atmosphere && <Chip label="атм" value={r.atmosphere} />}
                    </div>
                    <EvidenceLine text={r.evidence_text} conf={r.confidence} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Mentions */}
          <div className={`${CARD} p-4 lg:col-span-2`}>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <MentionBlock title="Материалы" items={ex.material_mentions} />
              <MentionBlock title="Оборудование" items={ex.equipment_mentions} />
              <MentionBlock title="Лаборатории" items={ex.lab_mentions} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ClaimColumn({
  title,
  accent,
  claims,
}: {
  title: string;
  accent: 'emerald' | 'amber';
  claims: ClaimFinding[];
}) {
  const ring =
    accent === 'emerald'
      ? 'border-l-emerald-500'
      : 'border-l-amber-500';
  return (
    <div>
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">
        {title} ({claims.length})
      </div>
      {claims.length === 0 ? (
        <p className="text-xs text-stone-400">нет</p>
      ) : (
        <div className="flex flex-col gap-2">
          {claims.map((c, i) => (
            <div
              key={i}
              className={`rounded-r-lg border-l-4 bg-stone-50 p-2 dark:bg-stone-800 ${ring}`}
            >
              <div className="text-sm text-stone-800 dark:text-stone-100">{c.statement}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {c.about_material && <Chip label="о материале" value={c.about_material} />}
                {c.about_property && <Chip label="о свойстве" value={c.about_property} />}
                {c.about_regime && <Chip label="о режиме" value={c.about_regime} />}
                {c.fine_class && <Chip label="класс" value={c.fine_class} />}
                {c.rule_agrees === false && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                    <AlertTriangle className="h-3 w-3" /> расходится с правилом
                  </span>
                )}
              </div>
              <EvidenceLine text={c.evidence_text} conf={c.confidence} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceLine({ text, conf }: { text: string; conf: number }) {
  return (
    <div className="mt-1 flex items-start gap-1 text-xs text-stone-500 dark:text-stone-400">
      <Quote className="mt-0.5 h-3 w-3 shrink-0" />
      <span className="italic">«{text}»</span>
      <span className="ml-auto shrink-0 tabular-nums">{pct(conf)}</span>
    </div>
  );
}

function MentionBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">
        {title} ({items.length})
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-stone-400">нет</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {items.map((m, i) => (
            <span
              key={i}
              className="rounded-md bg-stone-100 px-2 py-0.5 text-xs text-stone-700 dark:bg-stone-800 dark:text-stone-200"
            >
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
