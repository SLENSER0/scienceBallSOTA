import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  GitMerge,
  Layers,
  Loader2,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Workflow,
} from 'lucide-react';
import { api } from '../api';

// §8.10 — «Инкрементальный ER-шаг в ingestion + Dagster-asset entity_resolution».
// Делает наблюдаемым Step 6 конвейера (NORMALIZE → ER → VALIDATE): mentions нового
// документа резолвятся против уже существующих canonical без переобучения модели.
// Экран показывает конфиг шага, живой предпросмотр групп слияния по типу и запускает
// приёмочный сценарий: второй документ с AA2024 сливается в material:al-cu-2024 без
// дубликата (POST /api/v1/ingestion/er/demo). auto_merge применяется, review/separate —
// нет (не блокируют pipeline).

// --- local shapes for the §8.10 /ingestion/er/* endpoints ------------------
interface ERStepConfig {
  incremental: boolean;
  retrain_on_schedule: boolean;
  threshold: number;
  max_existing: number;
}
interface ERStepStatus {
  supported_types: string[];
  config: ERStepConfig;
  pipeline_position: string;
}
interface ERStepDecision {
  candidate_id: string;
  entity_type: string;
  decision: string;
  match_probability: number;
  canonical_id: string;
  members: string[];
  new_members: string[];
  existing_members: string[];
  merge_to_existing: boolean;
  blocked_by_review: boolean;
}
interface ERStepPreview {
  entity_type: string;
  n_existing: number;
  n_groups: number;
  by_decision: Record<string, number>;
  decisions: ERStepDecision[];
}
interface ERDemoResult {
  scenario: string;
  canonical_id: string;
  material_al2cu_before: number;
  material_al2cu_after: number;
  duplicate_removed: boolean;
  merged_without_duplicate: boolean;
  report: { by_decision?: Record<string, number>; merges_to_existing?: number };
  applied: { keep_id: string; drop_id: string; status: string }[];
}

const TYPES: { id: string; ru: string }[] = [
  { id: 'Material', ru: 'Материалы' },
  { id: 'Equipment', ru: 'Оборудование' },
  { id: 'Person', ru: 'Персоны' },
  { id: 'Lab', ru: 'Лаборатории' },
];

const DECISION: Record<string, { ru: string; cls: string }> = {
  auto_merge: { ru: 'авто-слияние', cls: 'text-verified border-verified/40' },
  review_needed: { ru: 'на ревью', cls: 'text-gap border-gap/40' },
  separate: { ru: 'раздельно', cls: 'text-faint border-line' },
};

function probColor(p: number): string {
  if (p >= 0.92) return 'bg-verified';
  if (p >= 0.7) return 'bg-gap';
  return 'bg-faint';
}

export function EntityResolutionStepView() {
  const [type, setType] = useState('Material');

  const status = useQuery<ERStepStatus>({
    queryKey: ['er-step-status'],
    queryFn: () => api.erStepStatus(),
  });

  const preview = useQuery<ERStepPreview>({
    queryKey: ['er-step-preview', type],
    queryFn: () => api.erStepPreview(type),
  });

  const demo = useMutation<ERDemoResult>({
    mutationFn: () => api.erStepDemo(),
    onSuccess: () => {
      // the demo mutates the graph — refresh the live preview
      preview.refetch();
    },
  });

  const cfg = status.data?.config;
  const groups = preview.data?.decisions ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-nickel">
          <Workflow size={16} className="text-copper" /> Инкрементальный ER-шаг конвейера
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-faint">
          {status.data?.pipeline_position ?? 'Step 6 (NORMALIZE → ER → VALIDATE)'} · Dagster asset
          entity_resolution · §8.10
        </div>

        {cfg && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className={`chip ${cfg.incremental ? 'text-verified border-verified/40' : 'text-faint'}`}>
              {cfg.incremental ? 'инкрементально' : 'полный прогон'}
            </span>
            <span className="chip text-faint">порог {cfg.threshold}</span>
            <span className="chip text-faint">
              переобучение: {cfg.retrain_on_schedule ? 'по расписанию' : 'выкл'}
            </span>
            <span className="chip text-faint">окно {cfg.max_existing}</span>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto grid max-w-4xl gap-5">
          {/* Acceptance demo — the star of §8.10 */}
          <div className="panel p-4">
            <div className="flex items-center gap-2">
              <GitMerge size={15} className="text-copper" />
              <span className="text-sm text-nickel">Приёмочный сценарий</span>
              <span className="ml-auto font-mono text-[10px] text-faint">
                AA2024 → material:al-cu-2024
              </span>
            </div>
            <p className="mt-2 text-xs text-muted">
              Второй документ вводит сплав под другой формой записи (AA2024). Инкрементальный ER
              сравнивает его с существующими canonical и, при авто-слиянии, Step 7 апсёртит по
              существующему id — дубликат не создаётся.
            </p>

            <button
              onClick={() => demo.mutate()}
              disabled={demo.isPending}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-copper/40 bg-copper/10 px-3 py-1.5 text-xs text-copper transition hover:bg-copper/20 disabled:opacity-40"
            >
              {demo.isPending ? (
                <>
                  <Loader2 size={13} className="animate-spin" /> прогон ER…
                </>
              ) : (
                <>
                  <PlayCircle size={13} /> Запустить сценарий
                </>
              )}
            </button>

            {demo.isError && (
              <div className="mt-2 font-mono text-[10px] text-contradiction">
                не удалось выполнить сценарий
              </div>
            )}

            {demo.data && <DemoResult r={demo.data} />}
          </div>

          {/* Live preview of duplicate groups by type */}
          <div className="panel p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Layers size={15} className="text-copper" />
              <span className="text-sm text-nickel">Группы слияния в графе</span>
              <button
                onClick={() => preview.refetch()}
                className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] text-faint hover:text-copper"
                title="пересчитать"
              >
                <RefreshCw size={11} className={preview.isFetching ? 'animate-spin' : ''} /> обновить
              </button>
            </div>

            <div className="mt-3 flex flex-wrap gap-1">
              {TYPES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setType(t.id)}
                  className={`chip ${type === t.id ? 'border-copper/50 text-copper' : 'text-faint'}`}
                >
                  {t.ru}
                </button>
              ))}
            </div>

            <div className="mt-3 font-mono text-[10px] text-faint">
              canonical: {preview.data?.n_existing ?? 0} · групп: {preview.data?.n_groups ?? 0}
              {preview.data?.by_decision &&
                Object.entries(preview.data.by_decision).map(([k, v]) => (
                  <span key={k} className="ml-2">
                    {DECISION[k]?.ru ?? k}: {v}
                  </span>
                ))}
            </div>

            <div className="mt-3 space-y-2">
              {preview.isLoading ? (
                <div className="flex items-center gap-2 font-mono text-xs text-faint">
                  <Loader2 size={13} className="animate-spin text-copper" /> прогон ER…
                </div>
              ) : preview.isError ? (
                <div className="text-sm text-contradiction">Не удалось загрузить предпросмотр.</div>
              ) : groups.length === 0 ? (
                <div className="py-6 text-center font-mono text-xs text-faint">
                  дубликатов для слияния не найдено
                </div>
              ) : (
                groups.map((g) => <GroupRow key={g.candidate_id} g={g} />)
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DemoResult({ r }: { r: ERDemoResult }) {
  const ok = r.merged_without_duplicate;
  return (
    <div className="mt-3 rounded-md border border-line bg-surface/50 p-3">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 size={15} className="text-verified" />
        ) : (
          <XCircle size={15} className="text-contradiction" />
        )}
        <span className={`text-xs ${ok ? 'text-verified' : 'text-contradiction'}`}>
          {ok ? 'Слито без дубликата' : 'Дубликат не устранён'}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        <Metric label="Al2Cu до" value={r.material_al2cu_before} />
        <Metric label="Al2Cu после" value={r.material_al2cu_after} accent={r.material_al2cu_after === 1} />
        <Metric label="слияний" value={r.report?.merges_to_existing ?? r.applied.length} />
      </div>
      {r.applied.length > 0 && (
        <div className="mt-2 space-y-1">
          {r.applied.map((a, i) => (
            <div key={i} className="flex items-center gap-1.5 font-mono text-[10px] text-faint">
              <span className="text-muted">{a.drop_id}</span>
              <GitMerge size={10} className="text-copper" />
              <span className="text-copper">{a.keep_id}</span>
              <span
                className={`ml-auto chip text-[9px] ${
                  a.status === 'merged' ? 'text-verified border-verified/40' : 'text-contradiction border-contradiction/40'
                }`}
              >
                {a.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="rounded bg-surface px-2 py-1.5">
      <div className={`metric text-lg ${accent ? 'text-verified' : 'text-copper'}`}>{value}</div>
      <div className="font-mono text-[9px] text-faint">{label}</div>
    </div>
  );
}

function GroupRow({ g }: { g: ERStepDecision }) {
  const d = DECISION[g.decision] ?? DECISION.separate;
  const pct = Math.round(g.match_probability * 100);
  return (
    <div className="rounded-md border border-line bg-surface/40 p-3">
      <div className="flex items-center gap-2">
        <span className={`chip ${d.cls}`}>{d.ru}</span>
        {g.merge_to_existing && (
          <span className="chip text-verified border-verified/40" title="сливается в существующий canonical">
            → в существующий
          </span>
        )}
        {g.blocked_by_review && (
          <span
            className="chip text-contradiction border-contradiction/40"
            title="в группе есть проверенный canonical — авто-слияние заблокировано (§8.9)"
          >
            <ShieldAlert size={11} /> защищено
          </span>
        )}
        <span className="ml-auto font-mono text-[10px] text-faint">{g.members.length} упом.</span>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
          <div className={`h-full ${probColor(g.match_probability)}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="metric text-sm text-copper">{pct}%</span>
      </div>

      <div className="mt-2 space-y-0.5">
        {g.members.map((m) => (
          <div
            key={m}
            className={`flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] ${
              m === g.canonical_id ? 'bg-copper/10 text-copper' : 'text-muted'
            }`}
          >
            {m}
            {m === g.canonical_id && (
              <span className="chip ml-1 border-copper/40 text-copper text-[9px]">canonical</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
