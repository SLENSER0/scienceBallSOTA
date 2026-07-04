import { create } from 'zustand';
import type { AnswerPayload, GraphNode, PrioritizedGap } from './types';

export type View =
  | 'chat'
  | 'ask'
  | 'library'
  | 'compare'
  | 'coverage'
  | 'gaps'
  | 'glossary'
  | 'entities'
  | 'curation'
  | 'admin'
  | 'advisor'
  | 'contradictions'
  | 'dashboard'
  | 'gapmap'
  // -- Batch-1 feature screens ---------------------------------------------
  | 'reasoning'
  | 'apples'
  | 'benchmark'
  | 'communities'
  | 'er_candidates'
  | 'erstep'
  | 'evidencepack'
  | 'figures'
  | 'gapplan'
  | 'gapmatrix'
  | 'hardness'
  | 'hitl'
  | 'largegraph'
  | 'linkpred'
  | 'livegds'
  | 'simlinks'
  | 'sourcetrust'
  | 'voi'
  | 'absence'
  | 'coverageMatrix'
  | 'missinglinks'
  // -- Batch-2 feature screens ---------------------------------------------
  | 'agenttrace'
  | 'runtransparency'
  | 'graphpath'
  | 'edgeanomalies'
  | 'schemaextract'
  | 'simembed'
  | 'similarMaterials'
  | 'suspects'
  | 'kghealth'
  | 'clustergraph'
  | 'corpusmap3d'
  | 'coveragesankey'
  | 'graphencoding'
  | 'evidencebbox'
  | 'extraction_eval'
  | 'mlner'
  | 'mlflow'
  | 'proseclaims'
  | 'qualityboard'
  | 'ragchecks'
  | 'targetdemo'
  | 'unitprov'
  // -- Batch-3 feature screens ---------------------------------------------
  | 'searchhl'
  | 'graphintegrity'
  | 'unitreview'
  | 'extractorrun'
  | 'warnings'
  | 'provcitations'
  | 'opsdash'
  | 'subgraphask'
  | 'graphtemplates'
  | 'figcaptions'
  | 'ocr'
  | 'batchingest'
  | 'ingestpipeline'
  | 'confidencefusion'
  | 'ereval'
  | 'reranklive'
  | 'experimentextract'
  | 'mentionresolve'
  | 'mergeundo'
  | 'evidenceinspector'
  | 'tablecorrection'
  // -- Batch-4 feature screens ---------------------------------------------
  | 'arbiterEvidence'
  | 'contradictionScan'
  | 'coveragedash'
  | 'curationdiffreagraph'
  | 'dod'
  | 'extractionrecall'
  | 'facetsearch'
  | 'corpusexplore'
  // Merged tabbed hubs (jury-facing consolidation)
  | 'graph-explore'
  | 'evidence-inspector'
  | 'source-trust'
  | 'curation-hub'
  | 'agent-reasoning'
  | 'facttimemachine'
  | 'goldendataset'
  | 'graphdiff'
  | 'langgraphstudio'
  | 'ltmemory'
  | 'newdocsensor'
  | 'pipelineemission'
  | 'pipelinelineage'
  | 'rangefacets'
  | 'rankingexplain'
  | 'regressiongate'
  | 'retrievaleval'
  | 'reviewtaskgen'
  | 'sourcecatalog'
  | 'subgraphchat'
  | 'verifiergate'
  // -- Batch-5 feature screens ---------------------------------------------
  | 'collaboration'
  | 'calibration'
  | 'dagsterassets'
  | 'ermetrics'
  | 'entitytimeline'
  | 'expertfeedback'
  | 'graphlegend'
  | 'localeswitcher'
  | 'materialsner'
  | 'pipelineagentdag'
  | 'propertytermreview';

interface AppState {
  view: View;
  setView: (v: View) => void;
  role: string;
  setRole: (r: string) => void;
  user: string | null;
  token: string | null;
  signIn: (user: string, role: string, token: string | null) => void;
  signOut: () => void;
  useLlm: boolean;
  setUseLlm: (v: boolean) => void;
  answer: AnswerPayload | null;
  setAnswer: (a: AnswerPayload | null) => void;
  selectedNode: GraphNode | null;
  setSelectedNode: (n: GraphNode | null) => void;
  // Deep-research state — lives in the app-level store so switching tabs mid-run
  // never loses the reasoning trace or the report (the «pages disappear» fix).
  deep: DeepResearchState;
  setDeep: (patch: Partial<DeepResearchState>) => void;
  resetDeep: (question: string) => void;
  // Gap-map agentic prioritization — cached in the store so leaving the tab and
  // coming back shows the already-computed cards instantly instead of re-running
  // the whole per-gap agent stream from scratch (same «pages disappear» fix as deep).
  gapMap: GapMapState;
  setGapMap: (patch: Partial<GapMapState>) => void;
  resetGapMap: () => void;
}

export type GapMapPhase = 'idle' | 'running' | 'done';
export interface GapMapState {
  phase: GapMapPhase;
  gaps: PrioritizedGap[];
  done: number;
  total: number;
}
const EMPTY_GAPMAP: GapMapState = { phase: 'idle', gaps: [], done: 0, total: 0 };

export interface DeepStage {
  node: string;
  label: string;
}
export interface DeepSource {
  title: string;
  url: string;
  snippet?: string;
  year?: number | null;
}
export interface GapAnalysis {
  question: string;
  have: { n_solutions: number; n_facts: number; n_papers: number; n_gaps: number };
  missing: string[];
  attention: string[];
  queries: string[];
  vision?: string;
}
export interface DeepResearchState {
  question: string;
  running: boolean;
  stages: DeepStage[];
  reasoning: string; // accumulated intermediate reasoning (node outputs)
  tokens: string; // live streamed tokens (the model «thinking»)
  report: string;
  engine: string;
  error: string;
  sources: DeepSource[]; // machine-readable found sources (for «Загрузить в граф»)
  promote: unknown | null; // last promote result {ingested, review} — persists across tabs
  analysis: GapAnalysis | null; // gap analysis (чего нет / на что обратить внимание)
}
const EMPTY_DEEP: DeepResearchState = {
  question: '',
  running: false,
  stages: [],
  reasoning: '',
  tokens: '',
  report: '',
  engine: '',
  error: '',
  sources: [],
  promote: null,
  analysis: null,
};

// Restore a persisted session so a reload keeps the user signed in.
const SESSION_KEY = 'sb.session';
function loadSession(): { user: string; role: string; token: string | null } | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
const saved = loadSession();

export const useStore = create<AppState>((set) => ({
  view: 'dashboard',
  setView: (view) => set({ view }),
  role: saved?.role ?? 'researcher',
  setRole: (role) => set({ role }),
  user: saved?.user ?? null,
  token: saved?.token ?? null,
  signIn: (user, role, token) => {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify({ user, role, token }));
    } catch {
      /* storage may be unavailable */
    }
    set({ user, role, token });
  },
  signOut: () => {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
    set({ user: null, token: null });
  },
  useLlm: true,
  setUseLlm: (useLlm) => set({ useLlm }),
  answer: null,
  setAnswer: (answer) => set({ answer }),
  selectedNode: null,
  setSelectedNode: (selectedNode) => set({ selectedNode }),
  deep: EMPTY_DEEP,
  setDeep: (patch) => set((s) => ({ deep: { ...s.deep, ...patch } })),
  resetDeep: (question) => set({ deep: { ...EMPTY_DEEP, question, running: true } }),
  gapMap: EMPTY_GAPMAP,
  setGapMap: (patch) => set((s) => ({ gapMap: { ...s.gapMap, ...patch } })),
  resetGapMap: () => set({ gapMap: { ...EMPTY_GAPMAP } }),
}));
