import { create } from 'zustand';
import type { AnswerPayload, GraphNode } from './types';

export type View = 'chat' | 'ask' | 'compare' | 'coverage' | 'gaps' | 'glossary';

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
}

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
}));
