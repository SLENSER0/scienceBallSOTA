import { create } from 'zustand';
import type { AnswerPayload, GraphNode } from './types';

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
  | 'admin';

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
}

export interface DeepStage {
  node: string;
  label: string;
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
  view: 'chat',
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
}));
