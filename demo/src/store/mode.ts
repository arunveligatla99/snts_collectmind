import { create } from "zustand";

export type DemoMode = "live" | "recorded";

export interface ModeState {
  mode: DemoMode;
  baseUrl: string;
  connectivity: "unknown" | "ok" | "down";
  setMode: (mode: DemoMode) => void;
  setConnectivity: (c: ModeState["connectivity"]) => void;
}

function initialMode(): DemoMode {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("mode");
    if (fromUrl === "live" || fromUrl === "recorded") return fromUrl;
  }
  const fromEnv = import.meta.env.VITE_DEMO_MODE;
  if (fromEnv === "live") return "live";
  return "recorded";
}

function initialBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
}

export const useModeStore = create<ModeState>((set) => ({
  mode: initialMode(),
  baseUrl: initialBaseUrl(),
  connectivity: "unknown",
  setMode: (mode) => set({ mode }),
  setConnectivity: (connectivity) => set({ connectivity }),
}));
