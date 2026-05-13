import { create } from "zustand";

export type PrincipalKey = "tenant-a" | "tenant-b" | "operator-alice";

export interface TokensState {
  tokens: Record<PrincipalKey, string | undefined>;
  active: PrincipalKey;
  setToken: (key: PrincipalKey, token: string | undefined) => void;
  setActive: (key: PrincipalKey) => void;
}

function fromEnv(): TokensState["tokens"] {
  return {
    "tenant-a": import.meta.env.VITE_TOKEN_TENANT_A,
    "tenant-b": import.meta.env.VITE_TOKEN_TENANT_B,
    "operator-alice": import.meta.env.VITE_TOKEN_OPERATOR_ALICE,
  };
}

export const useTokensStore = create<TokensState>((set) => ({
  tokens: fromEnv(),
  active: "tenant-a",
  setToken: (key, token) =>
    set((s) => ({ tokens: { ...s.tokens, [key]: token } })),
  setActive: (active) => set({ active }),
}));
