import { create } from "zustand";

import type { ChatMode, KeyMode, Provider } from "../types/api";

interface ModelChoice {
  provider: Provider;
  modelId: string;
  keyMode: KeyMode;
  localApiKey?: string;
}

interface AppState {
  chatMode: ChatMode;
  sessionId?: string;
  single: ModelChoice;
  left: ModelChoice;
  right: ModelChoice;
  crewName: string;
  agentOutputs: Record<string, { status: string; text: string; model: string; cost?: number; tokens?: number }>;
  synthesisText: string;
  crewTotalCost: number;
  crewBudget: number;
  sessionTokensIn: number;
  sessionTokensOut: number;
  sessionCost: number;
  setChatMode: (mode: ChatMode) => void;
  setSessionId: (sessionId: string) => void;
  setSingle: (next: Partial<ModelChoice>) => void;
  setLeft: (next: Partial<ModelChoice>) => void;
  setRight: (next: Partial<ModelChoice>) => void;
  setCrewName: (name: string) => void;
  updateAgentOutput: (agent: string, update: Partial<{ status: string; text: string; model: string; cost?: number; tokens?: number }>) => void;
  setSynthesisText: (text: string) => void;
  setCrewBudget: (budget: number) => void;
  setCrewTotalCost: (cost: number) => void;
  resetCrewState: () => void;
  addUsage: (tokensIn: number, tokensOut: number, cost: number) => void;
  resetUsage: () => void;
}

const defaultChoice: ModelChoice = {
  provider: "openrouter",
  modelId: "openrouter/auto",
  keyMode: "vault",
};

export const useAppStore = create<AppState>((set) => ({
  chatMode: "single",
  sessionId: undefined,
  single: defaultChoice,
  left: defaultChoice,
  right: { provider: "openrouter", modelId: "openrouter/free", keyMode: "vault" },
  crewName: "default",
  agentOutputs: {},
  synthesisText: "",
  crewTotalCost: 0,
  crewBudget: 5.0,
  sessionTokensIn: 0,
  sessionTokensOut: 0,
  sessionCost: 0,
  setChatMode: (mode) => set({ chatMode: mode }),
  setSessionId: (sessionId) => set({ sessionId }),
  setSingle: (next) => set((state) => ({ single: { ...state.single, ...next } })),
  setLeft: (next) => set((state) => ({ left: { ...state.left, ...next } })),
  setRight: (next) => set((state) => ({ right: { ...state.right, ...next } })),
  setCrewName: (name) => set({ crewName: name }),
  updateAgentOutput: (agent, update) =>
    set((state) => ({
      agentOutputs: {
        ...state.agentOutputs,
        [agent]: { ...({ status: "pending", text: "", model: "" }), ...state.agentOutputs[agent], ...update },
      },
    })),
  setSynthesisText: (text) => set((state) => ({ synthesisText: state.synthesisText + text })),
  setCrewBudget: (budget) => set({ crewBudget: budget }),
  setCrewTotalCost: (cost) => set({ crewTotalCost: cost }),
  resetCrewState: () => set({ agentOutputs: {}, synthesisText: "", crewTotalCost: 0 }),
  addUsage: (tokensIn, tokensOut, cost) =>
    set((state) => ({
      sessionTokensIn: state.sessionTokensIn + tokensIn,
      sessionTokensOut: state.sessionTokensOut + tokensOut,
      sessionCost: state.sessionCost + cost,
    })),
  resetUsage: () => set({ sessionTokensIn: 0, sessionTokensOut: 0, sessionCost: 0 }),
}));
