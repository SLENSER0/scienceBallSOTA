import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, FlaskConical, Fingerprint, Hash, Loader2, ShieldCheck } from 'lucide-react';

// Unit-normalization provenance for the Evidence Inspector (§7.9 / §5.2.6).
// Surfaces HOW a cited number was normalized: normalization_method
// (direct | converted | rule | manual) + the unit_registry_version that did it,
// plus canonical unit, physical dimension and curator flags — so a reader can
// trust and audit the normalization behind the value.
//
// Self-contained (no edits to api.ts): calls /api/v1/unit-provenance/* directly,
// replicating the app's role/session auth header. See UnitProvenanceView export
// for embedding into EvidenceDrawer.

interface UnitProvenance {
  property_id: string | null;
  value_raw: unknown;
  value: number | null;
  unit: string | null;
  value_normalized: number | null;
  normalized_unit: string | null;
  normalization_method: string;
  method_reason: string;
  unit_registry_version: string;
  dimension: string | null;
  policy_canonical_unit: string | null;
  registry_canonical_unit: string | null;
  in_range: boolean;
  review_needed: boolean;
  flags: string[];
  normalized_at: string;
}

interface RegistrySummary {
  unit_registry_version: string;
  unit_count: number;
  dimensions: string[];
  canonical_units: string[];
  methods: string[];
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

async function upReq<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

const METHOD_LABEL: Record<string, string> = {
  direct: 'прямое (без пересчёта)',
  converted: 'пересчёт единиц',
  rule: 'правило / допущение',
  manual: 'проверено куратором',
};

const METHOD_CLASS: Record<string, string> = {
  direct: 'border-copper/40 text-copper',
  converted: 'border-nickel/40 text-nickel-bright',
  rule: 'border-gap/40 text-gap',
  manual: 'border-copper/50 text-copper',
};

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

// Embeddable provenance card — pass a measurementId to fetch a stored node's
// provenance (used by the Evidence Inspector), else it renders the passed data.
export function UnitProvenanceCard({ prov }: { prov: UnitProvenance }) {
  const methodCls = METHOD_CLASS[prov.normalization_method] ?? 'border-line text-muted';
  return (
    <div className="panel p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className={`chip ${methodCls}`}>
          <ShieldCheck size={12} /> {prov.normalization_method}
        </span>
        <span className="text-xs text-muted">{METHOD_LABEL[prov.normalization_method] ?? ''}</span>
        {prov.review_needed && <span className="chip text-gap">нужна проверка</span>}
        {!prov.in_range && <span className="chip text-contradiction">вне диапазона</span>}
      </div>

      <div className="mb-3 flex flex-wrap items-baseline gap-2 text-sm">
        <span className="metric text-lg text-nickel-bright">{String(prov.value_raw ?? '—')}</span>
        {prov.unit && <span className="font-mono text-xs text-faint">{prov.unit}</span>}
        <ArrowRight size={14} className="text-faint" />
        <span className="metric text-lg text-nickel-bright">{fmt(prov.value_normalized)}</span>
        {prov.normalized_unit && (
          <span className="font-mono text-xs text-copper/80">{prov.normalized_unit}</span>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <dt className="text-faint">размерность</dt>
        <dd className="text-ink/90">{prov.dimension ?? '—'}</dd>
        <dt className="text-faint">canonical (policy)</dt>
        <dd className="font-mono text-ink/90">{prov.policy_canonical_unit ?? '—'}</dd>
        <dt className="text-faint">canonical (registry)</dt>
        <dd className="font-mono text-ink/90">{prov.registry_canonical_unit ?? '—'}</dd>
        <dt className="text-faint">свойство</dt>
        <dd className="font-mono text-ink/90">{prov.property_id ?? '—'}</dd>
      </dl>

      <p className="mt-3 text-[11px] italic text-muted">{prov.method_reason}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line/60 pt-2 text-[11px] text-faint">
        <span className="inline-flex items-center gap-1 font-mono" title="unit_registry_version (§7.11)">
          <Hash size={11} /> {prov.unit_registry_version}
        </span>
        {prov.normalized_at && <span className="font-mono">{prov.normalized_at}</span>}
        {prov.flags.map((f) => (
          <span key={f} className="chip text-gap">
            {f}
          </span>
        ))}
      </div>
    </div>
  );
}

// Fetch-and-render for a stored :Measurement node — drop into the Evidence
// Inspector next to a cited measurement.
export function MeasurementProvenance({ measurementId }: { measurementId: string }) {
  const [prov, setProv] = useState<UnitProvenance | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setProv(null);
    setErr(null);
    upReq<UnitProvenance>(`/api/v1/unit-provenance/measurement/${encodeURIComponent(measurementId)}`)
      .then((d) => live && setProv(d))
      .catch((e) => live && setErr(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [measurementId]);
  if (err) return <div className="text-xs text-contradiction">{err}</div>;
  if (!prov) return <div className="flex items-center gap-2 text-xs text-faint"><Loader2 size={12} className="animate-spin" /> нормализация…</div>;
  return <UnitProvenanceCard prov={prov} />;
}

const EXAMPLE_PROPS = [
  { id: '', label: '— без свойства —' },
  { id: 'prop:tensile_strength', label: 'предел прочности' },
  { id: 'prop:hardness', label: 'твёрдость' },
  { id: 'prop:current_density', label: 'плотность тока' },
  { id: 'prop:temperature', label: 'температура' },
];

// Full page: registry-version banner + interactive "explain" playground + a
// by-id lookup for stored measurements.
export function UnitProvenanceView() {
  const [registry, setRegistry] = useState<RegistrySummary | null>(null);
  useEffect(() => {
    upReq<RegistrySummary>('/api/v1/unit-provenance/registry')
      .then(setRegistry)
      .catch(() => setRegistry(null));
  }, []);

  const [valueRaw, setValueRaw] = useState('46.5');
  const [unit, setUnit] = useState('ksi');
  const [propertyId, setPropertyId] = useState('prop:tensile_strength');
  const [manual, setManual] = useState(false);

  const explain = useMutation<UnitProvenance, Error, void>({
    mutationFn: () =>
      upReq<UnitProvenance>('/api/v1/unit-provenance/explain', {
        method: 'POST',
        body: JSON.stringify({
          value_raw: valueRaw,
          unit: unit.trim() === '' ? null : unit,
          property_id: propertyId === '' ? null : propertyId,
          manual,
        }),
      }),
  });

  const [mid, setMid] = useState('');
  const lookup = useMutation<UnitProvenance, Error, void>({
    mutationFn: () =>
      upReq<UnitProvenance>(`/api/v1/unit-provenance/measurement/${encodeURIComponent(mid.trim())}`),
  });

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-4xl">
        <div className="eyebrow mb-1">объяснимость нормализации · §7.9</div>
        <h2 className="mb-1 font-display text-2xl font-semibold">
          Провенанс единиц измерения
        </h2>
        <p className="mb-5 max-w-2xl text-sm text-muted">
          Как получено нормализованное значение цитаты: способ нормализации
          (direct / converted / rule / manual), версия реестра единиц, каноническая
          единица и её размерность. Эти поля выводятся в Evidence Inspector, чтобы
          читатель мог доверять числу и проверить пересчёт.
        </p>

        {registry && (
          <div className="panel mb-6 flex flex-wrap items-center gap-3 p-3 text-xs">
            <span className="inline-flex items-center gap-1.5 font-mono text-copper/90">
              <Fingerprint size={13} /> {registry.unit_registry_version}
            </span>
            <span className="text-faint">·</span>
            <span className="text-muted">{registry.unit_count} канонических единиц</span>
            <span className="text-faint">·</span>
            <span className="text-muted">{registry.dimensions.length} размерностей</span>
            <div className="ml-auto flex flex-wrap gap-1">
              {registry.dimensions.map((d) => (
                <span key={d} className="chip text-faint">
                  {d}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* -- Explain playground ------------------------------------------- */}
        <div className="panel mb-6 p-4">
          <div className="eyebrow mb-3 text-faint">
            <FlaskConical size={12} className="inline" /> проверить нормализацию
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-faint">значение</span>
              <input
                value={valueRaw}
                onChange={(e) => setValueRaw(e.target.value)}
                className="metric w-28 rounded-md border border-line bg-surface/60 px-3 py-2 text-nickel-bright focus:border-copper/50 focus:outline-none"
                placeholder="46.5"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-faint">единица</span>
              <input
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                className="w-24 rounded-md border border-line bg-surface/60 px-3 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
                placeholder="ksi"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-faint">свойство</span>
              <select
                value={propertyId}
                onChange={(e) => setPropertyId(e.target.value)}
                className="rounded-md border border-line bg-surface/60 px-2 py-2 text-sm text-ink focus:border-copper/50 focus:outline-none"
              >
                {EXAMPLE_PROPS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5 pb-2 text-xs text-muted">
              <input
                type="checkbox"
                checked={manual}
                onChange={(e) => setManual(e.target.checked)}
                className="accent-copper"
              />
              manual
            </label>
            <button
              onClick={() => explain.mutate()}
              disabled={explain.isPending || valueRaw.trim() === ''}
              className="btn-copper ml-auto flex items-center gap-1.5"
            >
              {explain.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              Нормализовать
            </button>
          </div>
          {explain.error && (
            <div className="mt-3 text-sm text-contradiction">{explain.error.message}</div>
          )}
          {explain.data && (
            <div className="mt-4">
              <UnitProvenanceCard prov={explain.data} />
            </div>
          )}
        </div>

        {/* -- Lookup by stored measurement id ----------------------------- */}
        <div className="panel p-4">
          <div className="eyebrow mb-3 text-faint">
            <Fingerprint size={12} className="inline" /> провенанс узла Measurement
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <input
              value={mid}
              onChange={(e) => setMid(e.target.value)}
              className="flex-1 rounded-md border border-line bg-surface/60 px-3 py-2 font-mono text-xs text-ink placeholder:text-faint focus:border-copper/50 focus:outline-none"
              placeholder="measurement id, напр. Measurement:…"
            />
            <button
              onClick={() => mid.trim() && lookup.mutate()}
              disabled={lookup.isPending || mid.trim() === ''}
              className="btn-copper flex items-center gap-1.5"
            >
              {lookup.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              Показать
            </button>
          </div>
          {lookup.error && (
            <div className="mt-3 text-sm text-contradiction">{lookup.error.message}</div>
          )}
          {lookup.data && (
            <div className="mt-4">
              <UnitProvenanceCard prov={lookup.data} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
