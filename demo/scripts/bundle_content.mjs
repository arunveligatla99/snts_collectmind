#!/usr/bin/env node
// Build-time snapshot of constitution + ADRs + readiness reviews into
// demo/src/content/. The /docs route bundles `?raw` imports against that
// directory so the deployed UI ships an immutable copy with the git SHA of the
// commit it was built from, satisfying the "snapshot at SHA xxxx" footer.

import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..", "..");
const DEMO = resolve(HERE, "..");
const CONTENT = join(DEMO, "src", "content");

const SOURCES = [
  {
    from: ".specify/memory/constitution.md",
    to: "constitution.md",
  },
  {
    from: "docs/runbook/feature-001-readiness-review.md",
    to: "feature-001-readiness-review.md",
  },
  {
    from: "docs/runbook/feature-002-readiness-review.md",
    to: "feature-002-readiness-review.md",
  },
  {
    from: "docs/adr/README.md",
    to: "adrs/README.md",
  },
  {
    from: "docs/adr/0001-pin-covesa-vss.md",
    to: "adrs/0001-pin-covesa-vss.md",
  },
  {
    from: "docs/adr/0002-default-slm-qwen2-5-7b-instruct.md",
    to: "adrs/0002-default-slm-qwen2-5-7b-instruct.md",
  },
  {
    from: "docs/adr/0003-constrained-decoding-library.md",
    to: "adrs/0003-constrained-decoding-library.md",
  },
  {
    from: "docs/adr/0004-fingerprint-stub.md",
    to: "adrs/0004-fingerprint-stub.md",
  },
  {
    from: "docs/adr/0005-slm-hosting-topology.md",
    to: "adrs/0005-slm-hosting-topology.md",
  },
  {
    from: "docs/adr/0006-dev-default-policy-client.md",
    to: "adrs/0006-dev-default-policy-client.md",
  },
  {
    from: "docs/adr/0007-rls-restrictive-and-break-glass.md",
    to: "adrs/0007-rls-restrictive-and-break-glass.md",
  },
  {
    from: "docs/adr/0008-per-tenant-rate-limiting.md",
    to: "adrs/0008-per-tenant-rate-limiting.md",
  },
  {
    from: "docs/adr/0009-tenant-vehicle-ownership-store.md",
    to: "adrs/0009-tenant-vehicle-ownership-store.md",
  },
];

mkdirSync(join(CONTENT, "adrs"), { recursive: true });

for (const s of SOURCES) {
  const src = join(REPO_ROOT, s.from);
  const dst = join(CONTENT, s.to);
  try {
    copyFileSync(src, dst);
  } catch (e) {
    console.warn(`bundle_content: skipped ${s.from}: ${e.message}`);
  }
}

let sha = "local";
let date = new Date().toISOString().slice(0, 10);
try {
  sha = execSync("git rev-parse --short HEAD", { cwd: REPO_ROOT })
    .toString()
    .trim();
  date = execSync("git log -1 --format=%cs HEAD", { cwd: REPO_ROOT })
    .toString()
    .trim();
} catch {
  // git unavailable in build; keep defaults
}

const manifest = {
  sha,
  date,
  files: SOURCES.map((s) => s.to),
};
writeFileSync(
  join(CONTENT, "manifest.json"),
  JSON.stringify(manifest, null, 2) + "\n",
);
// Emit .env shim so Vite picks up the SHA at build time too.
const envOut = `VITE_SNAPSHOT_SHA=${sha}\nVITE_SNAPSHOT_DATE=${date}\n`;
writeFileSync(join(DEMO, ".env.snapshot"), envOut);
console.log(`bundle_content: ${SOURCES.length} files, SHA ${sha} (${date})`);
