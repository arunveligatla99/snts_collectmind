// Recorded-mode fixture resolver. Reads /recordings/index.json (built into the
// bundle via Vite's static import) and serves the captured response when the
// caller's (method, path) matches an entry. Path templating uses {param} tokens
// that are resolved against the actual call's params.

import index from "../../public/recordings/index.json";

export interface FixtureEntry {
  status: number;
  body: unknown;
  headers?: Record<string, string>;
  retryAfterSeconds?: number;
}

interface FixtureKey {
  method: string;
  path: string;
  principal?: string;
  body?: unknown;
}

const TABLE = index as unknown as Record<string, FixtureEntry>;

function keyOf(k: FixtureKey): string {
  const principal = k.principal ?? "anon";
  const body = k.body !== undefined ? JSON.stringify(k.body) : "";
  return `${k.method.toUpperCase()} ${k.path} ${principal} ${body}`.trim();
}

export function resolveFixture(k: FixtureKey): FixtureEntry | undefined {
  if (TABLE[keyOf(k)]) return TABLE[keyOf(k)];
  if (k.principal) {
    const principalFallback = `${k.method.toUpperCase()} ${k.path} ${k.principal}`;
    if (TABLE[principalFallback]) return TABLE[principalFallback];
  }
  return TABLE[`${k.method.toUpperCase()} ${k.path}`];
}

export function listFixtureKeys(): string[] {
  return Object.keys(TABLE);
}
