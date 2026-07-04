import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Code2,
  Database,
  FlaskConical,
  Loader2,
  Play,
  Sparkles,
} from 'lucide-react';

// §17.8 Graph query templates — parametric `material_regime_property` form → live
// subgraph + generated Cypher. Self-contained (no api.ts edits): it calls the
// graph-templates router directly with the same session-auth convention as api.ts.

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

interface PresetField {
  name: string;
  type: string;
  required: boolean;
  default: string | number | null;
}
interface Preset {
  key: string;
  title: string;
  query_type: string;
  description: string;
  fields: PresetField[];
  executable: boolean;
}
interface TemplatesResponse {
  templates: Preset[];
}

interface ExperimentRow {
  id: string;
  name: string;
  property: string | null;
  value: number | null;
  unit: string | null;
  valueRaw: string | null;
  confidence: number | null;
  polarity: string | null;
  domain: string | null;
  reviewStatus: string | null;
  evidenceIds: string[];
}
interface GapRow {
  id: string;
  name: string;
  gapType: string | null;
  domain: string | null;
  reviewStatus: string | null;
}
interface Summary {
  queryType: string;
  materialsMatched: number;
  measurements: number;
  regimes: number;
  gaps: number;
  evidence: number;
  text: string;
}
interface QueryContext {
  userQuery: string;
  filters: Record<string, unknown>;
  generatedCypher: string;
}
interface GraphPayload {
  nodes: unknown[];
  edges: unknown[];
}
interface RunResult {
  summary: Summary;
  experiments: ExperimentRow[];
  gaps: GapRow[];
  graph: GraphPayload;
  queryContext: QueryContext;
}

const FIELD_LABELS: Record<string, string> = {
  material: 'Материал',
  property: 'Свойство',
  operation: 'Операция режима',
  temperature_c: 'Температура, °C',
};

function fmtValue(v: number | null): string {
  if (v === null || v === undefined) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(3);
}

function StatChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel flex flex-col items-center px-4 py-2">
      <div className="font-mono text-xl text-copper">{value}</div>
      <div className="text-xs text-faint">{label}</div>
    </div>
  );
}

export function GraphQueryTemplatesView() {
  const [templates, setTemplates] = useState<Preset[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('material_regime_property');
  const [values, setValues] = useState<Record<string, string>>({});
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [showCypher, setShowCypher] = useState(true);

  useEffect(() => {
    apiGet<TemplatesResponse>('/api/v1/graph/templates')
      .then((d) => {
        setTemplates(d.templates);
        const first = d.templates.find((t) => t.executable) ?? d.templates[0];
        if (first) setSelectedKey(first.key);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const preset = useMemo(
    () => templates.find((t) => t.key === selectedKey),
    [templates, selectedKey],
  );

  // Seed defaults when the preset changes.
  useEffect(() => {
    if (!preset) return;
    const seed: Record<string, string> = {};
    for (const f of preset.fields) {
      seed[f.name] = f.default != null ? String(f.default) : '';
    }
    setValues(seed);
    setResult(null);
    setError(null);
  }, [preset]);

  const missingRequired = useMemo(() => {
    if (!preset) return true;
    return preset.fields.some((f) => f.required && !(values[f.name] ?? '').trim());
  }, [preset, values]);

  async function run() {
    if (!preset) return;
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { key: preset.key, min_confidence: minConfidence };
      for (const f of preset.fields) {
        const raw = (values[f.name] ?? '').trim();
        if (!raw) continue;
        body[f.name] = f.type === 'number' ? Number(raw) : raw;
      }
      const d = await apiPost<RunResult>('/api/v1/graph/templates/run', body);
      setResult(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 font-display text-2xl">
          <Sparkles size={22} className="text-copper" /> Шаблоны графовых запросов
        </h1>
        <p className="text-sm text-faint">
          Параметрическая форма ядра §6.2 «материал + режим → свойство»: заполните параметры,
          выполните запрос над живым графом и посмотрите сгенерированный Cypher (§17.8).
        </p>
      </header>

      {/* Preset picker + parameter form */}
      <div className="panel space-y-4 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Database size={16} className="text-faint" />
          <label className="text-xs uppercase text-faint">Шаблон</label>
          <select
            value={selectedKey}
            onChange={(e) => setSelectedKey(e.target.value)}
            className="rounded border border-line/60 bg-void/40 px-2 py-1 text-sm text-ink"
          >
            {templates.map((t) => (
              <option key={t.key} value={t.key} disabled={!t.executable}>
                {t.title}
                {t.executable ? '' : ' (скоро)'}
              </option>
            ))}
          </select>
        </div>

        {preset && <div className="text-xs text-faint">{preset.description}</div>}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {preset?.fields.map((f) => (
            <label key={f.name} className="flex flex-col gap-1">
              <span className="text-xs uppercase text-faint">
                {FIELD_LABELS[f.name] ?? f.name}
                {f.required && <span className="ml-1 text-copper">*</span>}
              </span>
              <input
                type={f.type === 'number' ? 'number' : 'text'}
                value={values[f.name] ?? ''}
                placeholder={f.default != null ? String(f.default) : f.required ? 'обязательно' : '—'}
                onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                className="rounded border border-line/60 bg-void/40 px-2 py-1 text-sm text-ink"
              />
            </label>
          ))}
          <label className="flex flex-col gap-1">
            <span className="text-xs uppercase text-faint">
              Мин. достоверность: {minConfidence.toFixed(2)}
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="mt-2"
            />
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={run}
            disabled={loading || missingRequired || !preset?.executable}
            className="flex items-center gap-2 rounded bg-copper px-4 py-2 text-sm font-medium text-void disabled:opacity-40"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            Выполнить запрос
          </button>
          {missingRequired && (
            <span className="text-xs text-faint">Заполните обязательные поля (*)</span>
          )}
        </div>
      </div>

      {error && (
        <div className="panel flex items-center gap-2 border border-red-500/40 p-3 text-sm text-red-300">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {result && (
        <div className="space-y-6">
          {/* Summary */}
          <div className="space-y-2">
            <div className="text-sm text-ink">{result.summary.text}</div>
            <div className="flex flex-wrap gap-2">
              <StatChip label="материалов" value={result.summary.materialsMatched} />
              <StatChip label="измерений" value={result.summary.measurements} />
              <StatChip label="режимов" value={result.summary.regimes} />
              <StatChip label="пробелов" value={result.summary.gaps} />
              <StatChip label="свидетельств" value={result.summary.evidence} />
              <StatChip label="узлов графа" value={result.graph.nodes.length} />
              <StatChip label="рёбер графа" value={result.graph.edges.length} />
            </div>
          </div>

          {/* Generated Cypher */}
          <div className="panel">
            <button
              onClick={() => setShowCypher((s) => !s)}
              className="flex w-full items-center gap-2 px-4 py-3 text-left font-display text-lg"
            >
              {showCypher ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
              <Code2 size={18} className="text-copper" /> Сгенерированный Cypher
            </button>
            {showCypher && (
              <div className="border-t border-line/40 p-4">
                <pre className="overflow-x-auto rounded bg-void/60 p-3 font-mono text-xs text-emerald-300">
                  {result.queryContext.generatedCypher}
                </pre>
                <div className="mt-3">
                  <div className="mb-1 text-xs uppercase text-faint">Параметры (bound)</div>
                  <pre className="overflow-x-auto rounded bg-void/40 p-2 font-mono text-xs text-faint">
                    {JSON.stringify(result.queryContext.filters, null, 2)}
                  </pre>
                </div>
                <div className="mt-2 text-xs text-faint">
                  Запрос: {result.queryContext.userQuery}
                </div>
              </div>
            )}
          </div>

          {/* Experiments (measurements + values + evidence) */}
          <div>
            <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
              <FlaskConical size={18} className="text-copper" /> Измерения и значения
            </h3>
            <div className="panel overflow-x-auto">
              {result.experiments.length === 0 ? (
                <div className="p-4 text-sm text-faint">Ничего не найдено под эти параметры.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line/60 text-left text-xs uppercase text-faint">
                      <th className="px-3 py-2">Свойство</th>
                      <th className="px-3 py-2 text-right">Значение</th>
                      <th className="px-3 py-2">Ед.</th>
                      <th className="px-3 py-2 text-right">Достов.</th>
                      <th className="px-3 py-2 text-right">Свидетельства</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.experiments.slice(0, 100).map((e) => (
                      <tr key={e.id} className="border-b border-line/30">
                        <td className="px-3 py-2 text-ink">{e.property ?? e.name}</td>
                        <td className="px-3 py-2 text-right font-mono text-ink">
                          {fmtValue(e.value)}
                        </td>
                        <td className="px-3 py-2 text-faint">{e.unit ?? '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {e.confidence != null ? e.confidence.toFixed(2) : '—'}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-faint">
                          {e.evidenceIds.length}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {result.experiments.length > 100 && (
              <div className="mt-1 text-xs text-faint">
                Показаны первые 100 из {result.experiments.length}.
              </div>
            )}
          </div>

          {/* Gaps */}
          {result.gaps.length > 0 && (
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-display text-lg">
                <AlertTriangle size={18} className="text-copper" /> Связанные пробелы
              </h3>
              <div className="panel divide-y divide-line/30">
                {result.gaps.map((g) => (
                  <div key={g.id} className="flex items-center justify-between px-3 py-2 text-sm">
                    <span className="text-ink">{g.name}</span>
                    {g.gapType && (
                      <span className="rounded bg-void/40 px-2 py-0.5 font-mono text-xs text-copper">
                        {g.gapType}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
