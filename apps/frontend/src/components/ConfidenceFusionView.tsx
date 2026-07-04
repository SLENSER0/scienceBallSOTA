import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowRight,
  CheckCircle2,
  Layers,
  Loader2,
  Plus,
  ShieldQuestion,
  TriangleAlert,
  X,
  XCircle,
} from 'lucide-react';
import { api, type ConfidenceFuseResult, type ConfidenceFusionLive, type FusedFact } from '../api';

// §6.13 Confidence-fusion в оркестраторе.
// Три независимых слоя извлечения — правило (rule), ML-модель (ml), LLM — оценивают
// один и тот же факт. Оркестратор сливает их уверенности: при согласии слоёв
// уверенность растёт (бонус за согласие), а при конфликте ЧИСЛОВЫХ значений факт
// детерминированно уходит в очередь ревью, и побеждает самый приоритетный слой
// (rule ≻ llm ≻ ml). Здесь это можно потрогать руками и увидеть на живом графе.

interface LayerInput {
  on: boolean;
  confidence: string;
  value: string;
}

interface FactInput {
  label: string;
  unit: string;
  rule: LayerInput;
  ml: LayerInput;
  llm: LayerInput;
}

const off = (): LayerInput => ({ on: false, confidence: '', value: '' });

const EXAMPLE_FACTS: FactInput[] = [
  {
    label: 'предел прочности (согласие)',
    unit: 'MPa',
    rule: { on: true, confidence: '0.8', value: '320' },
    ml: off(),
    llm: { on: true, confidence: '0.9', value: '321' },
  },
  {
    label: 'твёрдость (конфликт значений)',
    unit: 'HV',
    rule: { on: true, confidence: '0.9', value: '320' },
    ml: off(),
    llm: { on: true, confidence: '0.88', value: '500' },
  },
  {
    label: 'предел текучести (только LLM)',
    unit: 'MPa',
    rule: off(),
    ml: off(),
    llm: { on: true, confidence: '0.55', value: '210' },
  },
];

const LAYER_META: { key: 'rule' | 'ml' | 'llm'; label: string; ph: string }[] = [
  { key: 'rule', label: 'правило', ph: 'rule' },
  { key: 'ml', label: 'ML-модель', ph: 'ml' },
  { key: 'llm', label: 'LLM', ph: 'llm' },
];

const ACTION_STYLE: Record<string, { cls: string; icon: typeof CheckCircle2 }> = {
  auto_accept: { cls: 'text-nickel-bright', icon: CheckCircle2 },
  review: { cls: 'text-copper', icon: ShieldQuestion },
  reject: { cls: 'text-rust', icon: XCircle },
};

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const r = Math.round(v * 10000) / 10000;
  return String(r);
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function toFacts(inputs: FactInput[]) {
  return inputs.map((f) => {
    const layer = (l: LayerInput) =>
      l.on && l.confidence.trim() !== ''
        ? {
            confidence: Number(l.confidence),
            value: l.value.trim() === '' ? null : Number(l.value),
          }
        : undefined;
    return {
      label: f.label.trim() || null,
      unit: f.unit.trim() || null,
      rule: layer(f.rule),
      ml: layer(f.ml),
      llm: layer(f.llm),
    };
  });
}

function FactCard({ f }: { f: FusedFact }) {
  const style = ACTION_STYLE[f.review.action] ?? ACTION_STYLE.review;
  const Icon = style.icon;
  return (
    <div
      className={`panel p-4 ${f.conflict ? 'border-rust/50' : f.agreement_boost ? 'border-nickel/40' : ''}`}
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-medium text-ink">{f.label ?? f.id}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-faint">
            {f.sources.map((s) => (
              <span key={s} className="rounded bg-surface/70 px-1.5 py-0.5 text-muted">
                {s}
              </span>
            ))}
            {f.agreement_boost && (
              <span className="rounded bg-nickel/15 px-1.5 py-0.5 text-nickel-bright">
                +бонус за согласие
              </span>
            )}
            {f.conflict && (
              <span className="flex items-center gap-1 rounded bg-rust/10 px-1.5 py-0.5 text-rust">
                <TriangleAlert size={11} /> конфликт значений
              </span>
            )}
          </div>
        </div>
        <div className={`flex items-center gap-1.5 whitespace-nowrap text-sm ${style.cls}`}>
          <Icon size={16} /> {f.review.action_ru}
        </div>
      </div>

      {/* fused confidence bar */}
      <div className="mb-2">
        <div className="mb-1 flex items-center justify-between text-xs text-muted">
          <span>слитая уверенность</span>
          <span className="metric text-ink">{pct(f.fused_confidence)}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-surface/70">
          <div
            className={`h-full ${f.conflict ? 'bg-rust' : f.agreement_boost ? 'bg-nickel' : 'bg-copper'}`}
            style={{ width: pct(f.fused_confidence) }}
          />
        </div>
      </div>

      {/* reconciled value */}
      {f.reconciled_value !== null && (
        <div className="mb-2 flex items-center gap-2 text-sm">
          <span className="text-muted">итоговое значение:</span>
          <span className="metric text-nickel-bright">
            {fmt(f.reconciled_value)} {f.unit ?? ''}
          </span>
          {f.chosen_layer && (
            <span className="text-xs text-faint">
              <ArrowRight size={11} className="inline" /> слой «{f.chosen_layer}»
            </span>
          )}
          {f.conflict && f.spread > 0 && (
            <span className="text-xs text-rust">разброс {fmt(f.spread)}</span>
          )}
        </div>
      )}

      <p className="text-xs leading-relaxed text-faint">{f.explanation}</p>
    </div>
  );
}

export function ConfidenceFusionView() {
  const [facts, setFacts] = useState<FactInput[]>(EXAMPLE_FACTS);

  const fuse = useMutation<ConfidenceFuseResult, Error, void>({
    mutationFn: () => api.confidenceFuse(toFacts(facts)),
  });
  const live = useMutation<ConfidenceFusionLive, Error, void>({
    mutationFn: () => api.confidenceFusionLive(),
  });

  const setLayer = (i: number, key: 'rule' | 'ml' | 'llm', patch: Partial<LayerInput>) =>
    setFacts((fs) =>
      fs.map((f, j) => (j === i ? { ...f, [key]: { ...f[key], ...patch } } : f)),
    );
  const setFact = (i: number, patch: Partial<FactInput>) =>
    setFacts((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const addFact = () =>
    setFacts((fs) => [
      ...fs,
      { label: '', unit: '', rule: { on: true, confidence: '0.7', value: '' }, ml: off(), llm: off() },
    ]);
  const delFact = (i: number) => setFacts((fs) => fs.filter((_, j) => j !== i));

  const res = fuse.data;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="eyebrow mb-1">confidence-fusion · оркестратор · §6.13</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Слияние уверенности слоёв извлечения
        </h2>
        <p className="mb-6 max-w-3xl text-sm text-muted">
          Три независимых слоя — <b>правило</b>, <b>ML-модель</b>, <b>LLM</b> — оценивают один и
          тот же факт. Оркестратор сливает их уверенности: при согласии слоёв уверенность{' '}
          <b>растёт</b> (бонус за согласие), а при <b>конфликте числовых значений</b> факт
          детерминированно уходит в очередь ревью, и приоритет получает самый надёжный слой
          (правило ≻ LLM ≻ ML).
        </p>

        {/* -- Editable facts ------------------------------------------------ */}
        <div className="mb-4 space-y-3">
          {facts.map((f, i) => (
            <div key={i} className="panel p-4">
              <div className="mb-3 flex items-center gap-2">
                <Layers size={15} className="text-faint" />
                <input
                  value={f.label}
                  onChange={(e) => setFact(i, { label: e.target.value })}
                  placeholder="название факта (свойство / операция)"
                  className="min-w-0 flex-1 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
                />
                <input
                  value={f.unit}
                  onChange={(e) => setFact(i, { unit: e.target.value })}
                  placeholder="ед."
                  className="w-20 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
                />
                <button
                  onClick={() => delFact(i)}
                  className="rounded-md p-2 text-faint hover:bg-surface/60 hover:text-ink"
                  aria-label="удалить факт"
                >
                  <X size={15} />
                </button>
              </div>

              <div className="grid gap-2 sm:grid-cols-3">
                {LAYER_META.map(({ key, label, ph }) => {
                  const l = f[key];
                  return (
                    <div
                      key={key}
                      className={`rounded-md border px-2.5 py-2 ${l.on ? 'border-line bg-surface/40' : 'border-line/50 bg-transparent opacity-60'}`}
                    >
                      <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted">
                        <input
                          type="checkbox"
                          checked={l.on}
                          onChange={(e) => setLayer(i, key, { on: e.target.checked })}
                          className="accent-copper"
                        />
                        {label}
                      </label>
                      <div className="flex items-center gap-1.5">
                        <input
                          value={l.confidence}
                          onChange={(e) => setLayer(i, key, { confidence: e.target.value })}
                          disabled={!l.on}
                          type="number"
                          step="0.05"
                          min="0"
                          max="1"
                          placeholder="conf"
                          title="уверенность 0…1"
                          className="metric w-full rounded border border-line bg-surface/60 px-2 py-1 text-xs text-ink focus:border-copper/50 focus:outline-none disabled:opacity-50"
                        />
                        <input
                          value={l.value}
                          onChange={(e) => setLayer(i, key, { value: e.target.value })}
                          disabled={!l.on}
                          type="number"
                          placeholder={ph + ' знач.'}
                          title="числовое значение (для согласования)"
                          className="metric w-full rounded border border-line bg-surface/60 px-2 py-1 text-xs text-nickel-bright focus:border-copper/50 focus:outline-none disabled:opacity-50"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="mb-6 flex items-center justify-between">
          <button onClick={addFact} className="flex items-center gap-1.5 text-sm text-muted hover:text-ink">
            <Plus size={15} /> факт
          </button>
          <button
            onClick={() => fuse.mutate()}
            disabled={fuse.isPending}
            className="btn-copper flex items-center gap-1.5"
          >
            {fuse.isPending ? <Loader2 size={16} className="animate-spin" /> : <Layers size={16} />}
            Слить уверенности
          </button>
        </div>

        {fuse.isError && (
          <div className="panel mb-4 flex items-center gap-2 border-rust/40 p-3 text-sm text-rust">
            <TriangleAlert size={16} /> Не удалось выполнить слияние: {fuse.error.message}
          </div>
        )}

        {/* -- Fusion results ----------------------------------------------- */}
        {res && (
          <div className="mb-8">
            <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
              <span>фактов: <b className="text-ink">{res.total}</b></span>
              <span className="text-nickel-bright">автопринятие: {res.auto_accept}</span>
              <span className="text-copper">на ревью: {res.review}</span>
              <span className="text-rust">отклонено: {res.reject}</span>
              <span className="text-faint">
                бонусов: {res.boosted} · конфликтов: {res.conflicts}
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {res.facts.map((f) => (
                <FactCard key={f.id} f={f} />
              ))}
            </div>
          </div>
        )}

        {/* -- Live graph --------------------------------------------------- */}
        <div className="panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="eyebrow text-faint">на живом графе</div>
              <p className="mt-0.5 text-xs text-muted">
                Измерения группируются по (свойство · материал · единица) — один физический факт,
                извлечённый разными слоями — и сливаются тем же оркестратором.
              </p>
            </div>
            <button
              onClick={() => live.mutate()}
              disabled={live.isPending}
              className="flex items-center gap-1.5 whitespace-nowrap rounded-md border border-line px-3 py-2 text-sm text-muted transition-colors hover:border-copper/50 hover:text-ink disabled:opacity-40"
            >
              {live.isPending ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
              Загрузить
            </button>
          </div>

          {live.isError && (
            <div className="flex items-center gap-2 text-sm text-rust">
              <TriangleAlert size={16} /> {live.error.message}
            </div>
          )}

          {live.data && (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
                <span>измерений: <b className="text-ink">{live.data.total_measurements}</b></span>
                <span>мульти-слойных фактов: {live.data.multi_layer_clusters}</span>
                <span className="text-rust">конфликтов: {live.data.conflicts}</span>
                <span className="text-nickel-bright">с бонусом: {live.data.boosted}</span>
              </div>
              {live.data.clusters.length === 0 ? (
                <p className="text-sm text-faint">
                  Нет фактов, извлечённых ≥2 слоями (в текущем графе одно измерение = один слой).
                </p>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {live.data.clusters.map((c, i) => (
                    <div key={i}>
                      <div className="mb-1 text-xs text-faint">
                        {c.material ?? '—'} · {c.n_members} слоёв
                      </div>
                      <FactCard f={c.fusion} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
