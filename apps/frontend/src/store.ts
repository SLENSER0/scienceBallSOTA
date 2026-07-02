import { create } from 'zustand';
import type { AnswerPayload, GraphNode } from './types';

export type View = 'ask' | 'compare' | 'coverage' | 'gaps' | 'glossary';

interface AppState {
  view: View;
  setView: (v: View) => void;
  role: string;
  setRole: (r: string) => void;
  useLlm: boolean;
  setUseLlm: (v: boolean) => void;
  answer: AnswerPayload | null;
  setAnswer: (a: AnswerPayload | null) => void;
  selectedNode: GraphNode | null;
  setSelectedNode: (n: GraphNode | null) => void;
}

export const useStore = create<AppState>((set) => ({
  view: 'ask',
  setView: (view) => set({ view }),
  role: 'researcher',
  setRole: (role) => set({ role }),
  useLlm: true,
  setUseLlm: (useLlm) => set({ useLlm }),
  answer: null,
  setAnswer: (answer) => set({ answer }),
  selectedNode: null,
  setSelectedNode: (selectedNode) => set({ selectedNode }),
}));
