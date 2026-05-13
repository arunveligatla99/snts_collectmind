/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEMO_MODE?: "live" | "recorded";
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_TOKEN_TENANT_A?: string;
  readonly VITE_TOKEN_TENANT_B?: string;
  readonly VITE_TOKEN_OPERATOR_ALICE?: string;
  readonly VITE_SNAPSHOT_SHA?: string;
  readonly VITE_SNAPSHOT_DATE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.md?raw" {
  const src: string;
  export default src;
}
