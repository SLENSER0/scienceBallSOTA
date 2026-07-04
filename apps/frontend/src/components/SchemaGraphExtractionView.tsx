import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Filter, Play, ShieldCheck, TriangleAlert, XCircle } from 'lucide-react';
import { api } from '../api';

// §6.11 «PropertyGraphIndex + SchemaLLMPathExtractor»: schema-ограниченная
// граф-экстракция. Whitelisted типы узлов (§8.1) и связей (§8.2) плюс синтез
// Sample-путей дают чистый граф — off-schema триплеты отфильтровываются.
// Здесь показываем whitelist, «песочницу» фильтра и аудит живого графа (:8000).

interface Triple {
  subject: string;
  subject_type: string;
  relation: string;
  object: string;
  object_type: string;
}
interface PGSchema {
  entities: string[];
  relations: string[];
  validation_triples: [string, string, string][];
  entity_count: number;
  relation_count: number;
  triple_count: number;
  extractor: string;
  index: string;
  strict: boolean;
  llama_index_available: boolean;
}
interface ConstrainResult {
  kept: Triple[];
  rejected: (Triple & { reason: string })[];
  kept_count: number;
  rejected_count: number;
  total: number;
}
interface AuditSig {
  subject_type: string;
  relation: string;
  object_type: string;
  count: number;
  valid: boolean;
  in_extraction_whitelist: boolean;
}
interface AuditResult {
  profile: string;
  distinct_signatures: number;
  violating_signatures: number;
  total_edges_sampled: number;
  valid_edges: number;
  conformance: number;
  signatures: AuditSig[];
  violations: AuditSig[];
}

// Демо-кандидаты «как от LLM»: смесь валидных и мусорных триплетов, чтобы было
// видно, что нарушающие схему отбрасываются (критерий приёмки §6.11).
const DEMO_TRIPLETS: Triple[] = [
  { subject: 'exp:al-cu-aging', subject_type: 'Experiment', relation: 'USES_SAMPLE', object: 'sample:1', object_type: 'Sample' },
  { subject: 'sample:1', subject_type: 'Sample', relation: 'HAS_MATERIAL', object: 'Al-Cu', object_type: 'Material' },
  { subject: 'sample:1', subject_type: 'Sample', relation: 'PROCESSED_BY', object: 'aging 180C 2h', object_type: 'ProcessingRegime' },
  { subject: 'exp:al-cu-aging', subject_type: 'Experiment', relation: 'MEASURED', object: 'hardness=150HV', object_type: 'Measurement' },
  { subject: 'Al-Cu', subject_type: 'Material', relation: 'USES_SAMPLE', object: 'sample:1', object_type: 'Sample' },
  { subject: 'Al-Cu', subject_type: 'Material', relation: 'LIKES', object: 'Ivan', object_type: 'Person' },
  { subject: 'sample:1', subject_type: 'Sample', relation: 'PROCESSED_BY', object: 'Al-Cu', object_type: 'Material' },
];

const card = 'rounded-lg border border-white/10 bg-black/20 p-4';
const chip = 'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium';

function TripleRow({ t, ok, reason }: { t: Triple; ok: boolean; reason?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-2 rounded px-2 py-1.5 text-sm ${ok ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
      {ok ? <CheckCircle2 size={15} className="text-emerald-400" /> : <XCircle size={15} className="text-rose-400" />}
      <span className={`${chip} bg-white/5 text-nickel`}>{t.subject_type}</span>
      <span className="font-mono text-xs text-copper">{t.relation}</span>
      <span className={`${chip} bg-white/5 text-nickel`}>{t.object_type}</span>
      <span className="text-faint text-xs">
        {t.subject} → {t.object}
      </span>
      {!ok && reason && <span className="w-full text-xs text-rose-300/80">{reason}</span>}
    </div>
  );
}

export function SchemaGraphExtractionView() {
  const [triplets, setTriplets] = useState<Triple[]>(DEMO_TRIPLETS);
  const [raw, setRaw] = useState<string>(() => JSON.stringify(DEMO_TRIPLETS, null, 2));
  const [parseErr, setParseErr] = useState<string | null>(null);

  const schemaQ = useQuery<PGSchema>({
    queryKey: ['pg-schema'],
    queryFn: () => api.propertyGraphSchema(),
  });
  const auditQ = useQuery<AuditResult>({
    queryKey: ['pg-audit'],
    queryFn: () => api.propertyGraphAudit(),
    retry: false,
  });
  const constrainM = useMutation<ConstrainResult, Error, Triple[]>({
    mutationFn: (ts) => api.propertyGraphConstrain(ts),
  });

  const sch = schemaQ.data;
  const result = constrainM.data;

  function onRawChange(v: string) {
    setRaw(v);
    try {
      const parsed = JSON.parse(v);
      if (!Array.isArray(parsed)) throw new Error('ожидается JSON-массив триплетов');
      setTriplets(parsed);
      setParseErr(null);
    } catch (e) {
      setParseErr((e as Error).message);
    }
  }

  const conformancePct = useMemo(
    () => (auditQ.data ? Math.round(auditQ.data.conformance * 1000) / 10 : null),
    [auditQ.data],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <ShieldCheck className="text-copper" size={22} />
          <h1 className="text-xl font-semibold text-nickel">Схема-ограниченная граф-экстракция</h1>
        </div>
        <p className="text-sm text-faint">
          PropertyGraphIndex + SchemaLLMPathExtractor (§6.11). Экстрактор ограничен whitelist-типами
          узлов (§8.1) и связей (§8.2); off-schema триплеты отбрасываются, а Sample-путь синтезируется —
          чистый граф без мусора.
        </p>
      </header>

      {/* Whitelist schema */}
      <section className={card}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-nickel">
            <Filter size={16} /> Whitelist схемы
          </h2>
          {sch && (
            <span className="text-xs text-faint">
              {sch.entity_count} типов узлов · {sch.relation_count} связей · {sch.triple_count} путей ·{' '}
              <span className={sch.llama_index_available ? 'text-emerald-400' : 'text-amber-400'}>
                {sch.llama_index_available ? 'LlamaIndex активен' : 'фильтр без LLM'}
              </span>
            </span>
          )}
        </div>
        {schemaQ.isLoading && <p className="text-sm text-faint">Загрузка схемы…</p>}
        {schemaQ.isError && <p className="text-sm text-rose-400">Не удалось загрузить схему.</p>}
        {sch && (
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs uppercase tracking-wide text-faint">Типы узлов (§8.1)</div>
              <div className="flex flex-wrap gap-1.5">
                {sch.entities.map((e) => (
                  <span key={e} className={`${chip} bg-copper/15 text-copper`}>{e}</span>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs uppercase tracking-wide text-faint">Типы связей (§8.2)</div>
              <div className="flex flex-wrap gap-1.5">
                {sch.relations.map((r) => (
                  <span key={r} className={`${chip} bg-white/5 font-mono text-nickel`}>{r}</span>
                ))}
              </div>
            </div>
            <details className="text-sm">
              <summary className="cursor-pointer text-xs text-faint hover:text-nickel">
                Разрешённые пути (subject)-[rel]-&gt;(object) — {sch.triple_count}
              </summary>
              <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
                {sch.validation_triples.map(([s, r, o], i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs">
                    <span className={`${chip} bg-white/5 text-nickel`}>{s}</span>
                    <span className="font-mono text-copper">{r}</span>
                    <span className={`${chip} bg-white/5 text-nickel`}>{o}</span>
                  </div>
                ))}
              </div>
            </details>
          </div>
        )}
      </section>

      {/* Constrain playground */}
      <section className={card}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-nickel">Песочница фильтра (strict=true)</h2>
          <button
            onClick={() => constrainM.mutate(triplets)}
            disabled={!!parseErr || constrainM.isPending}
            className="inline-flex items-center gap-1.5 rounded bg-copper/20 px-3 py-1.5 text-sm text-copper hover:bg-copper/30 disabled:opacity-50"
          >
            <Play size={14} /> Прогнать через схему
          </button>
        </div>
        <p className="mb-2 text-xs text-faint">
          Кандидатные триплеты (как от LLM). Валидные проходят, нарушающие схему — отбрасываются с причиной.
        </p>
        <textarea
          value={raw}
          onChange={(e) => onRawChange(e.target.value)}
          spellCheck={false}
          rows={8}
          className="w-full rounded border border-white/10 bg-black/40 p-2 font-mono text-xs text-nickel focus:border-copper/50 focus:outline-none"
        />
        {parseErr && <p className="mt-1 text-xs text-rose-400">JSON: {parseErr}</p>}

        {result && (
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                <CheckCircle2 size={14} /> Прошли ({result.kept_count})
              </div>
              <div className="space-y-1">
                {result.kept.map((t, i) => (
                  <TripleRow key={i} t={t} ok />
                ))}
                {result.kept.length === 0 && <p className="text-xs text-faint">—</p>}
              </div>
            </div>
            <div>
              <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-rose-400">
                <XCircle size={14} /> Отброшены ({result.rejected_count})
              </div>
              <div className="space-y-1">
                {result.rejected.map((t, i) => (
                  <TripleRow key={i} t={t} ok={false} reason={t.reason} />
                ))}
                {result.rejected.length === 0 && <p className="text-xs text-faint">—</p>}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Live-graph audit */}
      <section className={card}>
        <h2 className="mb-3 text-sm font-semibold text-nickel">Аудит живого графа (§8-валидация)</h2>
        {auditQ.isLoading && <p className="text-sm text-faint">Сканирование графа…</p>}
        {auditQ.isError && (
          <p className="text-sm text-amber-400">
            Аудит доступен только на server-профиле (Neo4j :8000). Песочница выше работает без БД.
          </p>
        )}
        {auditQ.data && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div>
                <span className="text-2xl font-semibold text-emerald-400">{conformancePct}%</span>
                <span className="ml-1 text-xs text-faint">соответствие §8.2</span>
              </div>
              <div className="text-xs text-faint">
                {auditQ.data.distinct_signatures} сигнатур · {auditQ.data.total_edges_sampled} рёбер ·{' '}
                <span className={auditQ.data.violating_signatures ? 'text-rose-400' : 'text-emerald-400'}>
                  {auditQ.data.violating_signatures} нарушающих
                </span>
              </div>
            </div>
            {auditQ.data.violations.length > 0 && (
              <div>
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-rose-400">
                  <TriangleAlert size={14} /> Off-schema сигнатуры (их бы отфильтровал экстрактор)
                </div>
                <div className="space-y-1">
                  {auditQ.data.violations.map((s, i) => (
                    <TripleRow
                      key={i}
                      t={{ subject: `×${s.count}`, subject_type: s.subject_type, relation: s.relation, object: '', object_type: s.object_type }}
                      ok={false}
                      reason={`${s.count} рёбер с сигнатурой вне §8.2`}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
