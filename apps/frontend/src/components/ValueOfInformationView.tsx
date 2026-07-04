import { useQuery } from '@tanstack/react-query';
import { FlaskConical, Loader2, Gauge, Lightbulb } from 'lucide-react';
import { api } from '../api';

// «Карта неизвестного»: ранжирование по ценности информации (§25.11). Absence-слой уже
// считает p_extractor_missed для каждой пустой ячейки (материал × свойство). Здесь мы
// оцениваем каждую бинарной энтропией H(p) — value of information. VoI максимальна при
// p=0.5 (максимально неоднозначная ячейка: замер сильнее всего снизит неопределённость)
// и падает к 0 у уверенных концов. R&D-лид видит, КУДА ставить эксперимент — а не просто
// список дыр. Отличается от «риска пропуска»: ячейка с p=0.95 рискованна, но VoI низкая
// (мы и так почти уверены — мерить нечего).

interface VoICell {
  material_id: string;
  material_name: string;
  property_name: string;
  p_extractor_missed: number;
  voi: number;
  voi_pct: number;
  absence_verdict: string | null;
  verdict_ru: string | null;
  p_truly_absent: number | null;
}

interface VoIResponse {
  schema_version: string;
  scanned: number;
  total_voi: number;
  verdict_labels: Record<string, string>;
  recommended_experiment: VoICell | null;
  top: VoICell[];
  cells: VoICell[];
}

function fetchVoi(topN: number): Promise<VoIResponse> {
  return api.absenceValueOfInformation(topN);
}

const VERDICT_TONE: Record<string, string> = {
  genuine_gap: '#8FA3B0',
  possible_miss: '#E0A23C',
  abstain: '#B08FD0',
  retracted: '#E5484D',
};

function voiTone(pct: number): string {
  if (pct >= 80) return '#E0A23C';
  if (pct >= 45) return '#C08A4A';
  return '#8FA3B0';
}

export function ValueOfInformationView() {
  const q = useQuery({
    queryKey: ['gaps-voi', 30],
    queryFn: () => fetchVoi(30),
    staleTime: 5 * 60_000,
  });
  const data = q.data;
  const cells = data?.cells ?? [];
  const rec = data?.recommended_experiment ?? null;

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="eyebrow mb-1">карта неизвестного · ценность информации</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <FlaskConical size={22} className="text-copper" /> Куда ставить эксперимент
        </h1>
        <p className="mt-1 text-sm text-faint">
          Каждый неизвестный замер (материал × свойство) оценивается{' '}
          <span className="font-mono text-copper">value of information</span> — бинарной энтропией
          H(p) вероятности пропуска извлечения. VoI максимальна у максимально неоднозначных ячеек:
          именно такой замер сильнее всего снизит неопределённость «карты неизвестного».
        </p>

        {q.isLoading ? (
          <div className="mt-8 flex items-center gap-2 font-mono text-sm text-faint">
            <Loader2 size={15} className="animate-spin text-copper" /> считаем ценность информации…
          </div>
        ) : q.isError ? (
          <div className="panel mt-8 py-8 text-center font-mono text-[11px] text-red-400">
            не удалось загрузить ранжирование VoI
          </div>
        ) : (
          <>
            {rec && rec.voi_pct > 0 && (
              <div className="panel mt-5 border-copper/40 bg-copper/5 p-4">
                <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-copper-bright">
                  <Lightbulb size={12} /> рекомендованный эксперимент
                </div>
                <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="text-base font-medium text-ink">{rec.material_name}</span>
                  <span className="text-faint">·</span>
                  <span className="font-mono text-sm text-copper">{rec.property_name}</span>
                </div>
                <div className="mt-1 text-[13px] text-muted">
                  Ценность информации {rec.voi_pct}% — измерение этой ячейки снимет больше всего
                  неопределённости. Риск пропуска извлечения{' '}
                  {Math.round(rec.p_extractor_missed * 100)}%
                  {rec.verdict_ru ? ` · вердикт: ${rec.verdict_ru}` : ''}.
                </div>
              </div>
            )}

            <div className="mt-4 flex items-center gap-3 font-mono text-[10px] text-faint">
              <span className="flex items-center gap-1">
                <Gauge size={11} /> отсканировано ячеек: {data?.scanned ?? 0}
              </span>
              <span>суммарная VoI: {(data?.total_voi ?? 0).toFixed(2)} бит</span>
            </div>

            <div className="mt-3 space-y-2">
              {cells.map((c, i) => (
                <VoIRow key={`${c.material_id}:${c.property_name}`} c={c} rank={i + 1} />
              ))}
              {cells.length === 0 && (
                <div className="panel py-10 text-center font-mono text-[11px] text-faint">
                  неизвестных ячеек не найдено — карта покрыта
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function VoIRow({ c, rank }: { c: VoICell; rank: number }) {
  const tone = voiTone(c.voi_pct);
  const vTone = (c.absence_verdict && VERDICT_TONE[c.absence_verdict]) || '#8FA3B0';
  return (
    <div className="panel p-3">
      <div className="flex items-start gap-3">
        <div className="flex flex-col items-center">
          <span className="metric text-lg" style={{ color: tone }}>
            {c.voi_pct}
          </span>
          <span className="font-mono text-[9px] text-faint">#{rank}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-sm font-medium text-ink">{c.material_name}</span>
            <span className="text-faint">·</span>
            <span className="font-mono text-[13px] text-copper">{c.property_name}</span>
            {c.verdict_ru && (
              <span className="chip" style={{ color: vTone, borderColor: `${vTone}55` }}>
                {c.verdict_ru}
              </span>
            )}
          </div>
          {/* VoI bar */}
          <div className="mt-2 flex items-center gap-1.5">
            <span className="font-mono text-[9px] uppercase tracking-wide text-faint">VoI</span>
            <div className="h-1.5 w-40 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full"
                style={{ width: `${c.voi_pct}%`, backgroundColor: tone }}
              />
            </div>
            <span className="font-mono text-[9px] text-faint">{c.voi.toFixed(2)} бит</span>
            <span className="ml-2 font-mono text-[9px] text-faint">
              p(пропуск) {Math.round(c.p_extractor_missed * 100)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
