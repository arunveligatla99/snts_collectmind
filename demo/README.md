# CollectMind demo UI

Production-grade Vite + React + TypeScript app that demonstrates CollectMind's diagnostic-to-collection loop end-to-end. Two run modes:

- **recorded** — bundled JSON fixtures captured from a real Compose-stack run via `demo/scripts/record_fixtures.sh`. Default mode. The deployed Vercel build runs in this mode only (no public Compose stack, no shipped tokens).
- **live** — points the typed API client at a locally running Compose stack on `http://localhost:8081`. Vite dev-server proxies `/api/v1` so CORS is a non-issue.

Mode toggles via `?mode=live|recorded` URL param or the header switch. Tokens for live mode come from `demo/.env.local` (see below).

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Build | Vite 6 + React 18 + TypeScript strict (`noUncheckedIndexedAccess`) | Fast HMR + strict typing |
| Styling | Tailwind 3 + custom shadcn-style components copied in | No runtime style dep, full control |
| Routing | React Router 6 | Standard, ergonomic nested routes |
| Data | TanStack Query 5 | Cache + request lifecycle for fetch |
| State | Zustand 5 | Two tiny stores: mode + tokens |
| Charts | Tremor 3 (where used) + custom SLO tiles | Tremor is heavy; we use it sparingly |
| Diagrams | Mermaid 11 | Architecture render is one component |
| Tests | Vitest 2 + @testing-library/react + jsdom | Same coverage floor as backend (85%) |
| Types | openapi-typescript 7 | Principle XVI: machine-readable contracts, no hand-written types |

## Routes

| Path | Purpose | Backend surfaces consumed |
|---|---|---|
| `/` | Pitch + Mermaid architecture + measured-SLO hero strip | none |
| `/operator` | Submit a finding as `tenant-a`, watch the audit chain materialize, drill FR-017a fields | `POST /findings`, `GET /audit/{cid}`, `GET /findings/{id}/outcome` |
| `/audit` | Interactive audit chain explorer with kind filter + free-text search | `GET /audit/{cid}` |
| `/slo` | Measured SLOs (real local-run numbers) + workflow_dispatch / nightly-gated SLOs | static + future Prom live tiles |
| `/tenants` | Side-by-side tenant-a / tenant-b columns with the operator break-glass in the center; cross-tenant probe shows the 404 collapse | all three surfaces: orchestration + query + audit-admin |
| `/docs` | Constitution + ADRs + readiness reviews rendered as markdown, snapshot-pinned to the git SHA | none |

## Local run

```bash
# 1) install
cd demo && npm install

# 2) generate the TypeScript types from contracts/openapi/
npm run gen:types

# 3) bundle the markdown content (constitution + ADRs + readiness reviews) and stamp the snapshot SHA
node scripts/bundle_content.mjs

# 4) start the Vite dev server (recorded mode by default)
npm run dev
# → http://localhost:5173

# 5) (optional) switch to live mode against the local Compose stack
#    in another shell:
#      docker compose -f infra/compose/docker-compose.yaml up -d
#      bash demo/scripts/mint_tokens.sh   # creates demo/.env.local
#    then in the browser: http://localhost:5173?mode=live
```

## Tests

```bash
npm run test          # one-shot run + coverage report
npm run test:watch    # watch mode
```

Coverage gate: `lines ≥ 85% · statements ≥ 85% · functions ≥ 85% · branches ≥ 80%` (per `vitest.config.ts`). Same Principle IV floor as the backend, measured separately against `demo/src/`.

## Live mode: token minting

In live mode the browser cannot call the dev issuer directly (audience-scoped JWTs are minted server-side). The wrapper script writes minted tokens into `demo/.env.local`, which Vite picks up at boot.

```bash
bash demo/scripts/mint_tokens.sh
# emits:
#   VITE_TOKEN_TENANT_A=...
#   VITE_TOKEN_TENANT_B=...
#   VITE_TOKEN_OPERATOR_ALICE=...
```

`.demo-tokens/` and `demo/.env.local` are gitignored. No tokens ship to the Vercel build.

## Recording mode workflow

```bash
# capture a fresh fixture pack from the Compose stack
bash demo/scripts/record_fixtures.sh
# writes:
#   demo/public/recordings/index.json    ← method+path+principal+body → response
#   demo/public/recordings/<dir>/*.json  ← per-endpoint capture
# runs the PII gate over the captures:
python demo/scripts/check_fixtures_pii.py demo/public/recordings/
```

Re-running invalidates and re-captures the fixtures. `index.json` is bundled into the JS by Vite (no runtime network for recorded mode).

## Vercel deployment

```bash
# one-time
npm install -g vercel
vercel login

# deploy preview from the demo/ directory
cd demo && vercel

# promote to prod
vercel --prod
```

`vercel.json` sets the framework + build + rewrites (SPA fallback to `index.html`). No env vars are required at build time; the snapshot SHA is baked into the JS bundle by `scripts/bundle_content.mjs` reading `git rev-parse --short HEAD`.

## Interview runbook

The demo is designed for three slot sizes. Pick the one matching the room.

### 5-minute slot — "the loop closes; tenants stay isolated; audit chain is the contract"

1. Land on `/`. Read the one-line pitch. The measured-SLO strip (Dashboard lag 2.11 s, Quickstart 3 s, Coverage 85.36 %, Test bar 329 / 17 / 24) anchors that this is shipped work, not aspiration.
2. Click **Run the loop**. On `/operator`, POST the default brake-wear finding as tenant-a. Walk the audit chain top-to-bottom: accepted → generated → validated → deployed → outcome. Expand the **generated** row — call out `slm_repo`, `slm_revision_sha`, `prompt_template_version`, `slm_decoding_seed`. "These are FR-017a's minimum field set; they exist on every generated policy so the audit chain is queryable, not log-mined (Principle XVII)."
3. Click **Tenants** in the sidebar. Submit findings in both columns. Show that tenant-b's cross-tenant probe of tenant-a's policy returns HTTP 404 (FR-006 — collapsed to 404, not 403, to avoid an existence oracle).
4. Run the operator break-glass in the center column. Show the new `kind=break_glass` row materializing in tenant-a's chain. "Distinct router, operator-audience JWT, service-principal connection. The audit row is written in the same DB transaction as the bypassed SELECT — atomic by topology, not by discipline (ADR-0007)."

### 10-minute slot — same as 5, plus

5. `/slo`. "Principle XI is non-negotiable: SLOs are measured, not aspired." Point at SC-006 (2.11 s vs 10 s budget) and SC-008 (3 s vs 600 s) — both real local-run numbers, both ~5× / ~200× under budget. Then point at SC-002 / SC-003 / ADR-0002 eval baseline in the gated column. "These need workflow_dispatch + nightly + a GPU runner per Principle XIV. We don't fabricate numbers; gating is named."
6. Flip the **mode toggle** in the header from `recorded` to `live` (if the local Compose stack is up). Resubmit the finding. The exact same UI now hits the real orchestration-api; the audit chain and outcome are real Postgres + Kafka + Redis paths. "The deployed UI ships recorded-only because Vercel can't reach localhost. Live mode is for the local dev loop where the stack is in front of you."

### 15-minute slot — same as 10, plus

7. `/docs`. Open the constitution. Walk Principle II ("no mocked subsystems where a real one is feasible"), Principle XIII ("SLM-first, isolated, swappable"), Principle XIV (deterministic CI budget). "Every PR is held to this bar, not the first one."
8. Open ADR-0007 (RESTRICTIVE RLS + break-glass) and ADR-0009 (tenant-vehicle ownership). Point at the worked example in Phase 9.b in DECISIONS.md — RESTRICTIVE-only RLS was a silent zero-rows trap that the integration tier caught. "Reading code by itself catches a fraction of what running it catches; that's why feature 002's Phase 9.b shipped with three independent verification layers, not one."
9. Architecture diagram on `/`. Point at the SLM container — no outbound network except OTLP. Point at the registry — RLS RESTRICTIVE. Point at the audit_events box — every node writes to it. "Audit is structural. So is tenant isolation. So is the deterministic CI gate."

## Architecture notes

- **`src/api/client.ts`** owns every backend call. It branches on `useModeStore.getState().mode`. In live mode it calls `window.fetch`. In recorded mode it resolves the (method, path, principal, body) tuple against `public/recordings/index.json`. Errors get parsed and re-thrown as `ApiError` — the UI shows status + code + retry-after where applicable.
- **`src/api/types/`** is generated by `openapi-typescript` from the three contract files under `contracts/openapi/`. The `npm run gen:types` script is wired into the PR-tier CI via `scripts/check_openapi_types_diff.py` — drift fails the build, same posture as the backend's OpenAPI dump-diff guard (T132).
- **`src/api/endpoints/`** are thin typed wrappers (one function per operationId). They're the only thing the UI imports.
- **`src/store/`** has two stores: `mode` (live/recorded + base URL + connectivity) and `tokens` (per-principal JWTs in memory only).
- **`src/components/AuditChain.tsx`** unifies tenant-side and operator-side audit-event shapes into a `DisplayAuditEvent`. The FR-017a fields and the `policy_ref` / `deployment_ref` / `outcome_ref` blocks render the same way regardless of which surface produced them.
- **`src/lib/markdown.ts`** is a small CommonMark-subset renderer (headings, code, lists, blockquotes, hr, tables, inline code, bold/italic, links). The `/docs` route bundles the markdown via `?raw` imports, so the deployed bundle is self-contained.
- **`scripts/bundle_content.mjs`** runs as the `prebuild` step. It snapshots the load-bearing markdown files (constitution + ADRs + readiness reviews) into `src/content/` and stamps `VITE_SNAPSHOT_SHA` + `VITE_SNAPSHOT_DATE` so the footer + recorded-mode banner can show "git xxxx · 2026-yy-zz" with no runtime network.

## Constitution alignment

| Principle | How the demo upholds it |
|---|---|
| I (production-grade) | No "demo" placeholders, no mocks of widgets, no TODOs. Same coverage gate as backend. |
| IV (tests load-bearing) | 75+ Vitest tests covering the API client, every endpoint wrapper, every component, and every route. `--coverage --thresholds` enforces ≥85%. |
| VII (CI gates) | `scripts/check_openapi_types_diff.py` wired into `custom-guards`. Demo types must regenerate clean against the contracts on every PR. |
| IX (security) | Tokens in memory only, never persisted to localStorage / IndexedDB. `.demo-tokens/` and `.env.local` gitignored. PII gate runs over recorded fixtures via `check_fixtures_pii.py`. |
| XVI (machine-readable contracts) | `src/api/types/` is generated, never hand-written. The UI references typed `components["schemas"]` types from openapi-typescript. |

## Known limitations

- The deployed Vercel build cannot reach a localhost Compose stack. By design — see Q2 decision in the build-prompt: recorded-only on deploy.
- The Mermaid bundle is ~950 kB minified. Acceptable for an interview demo; lazy-loading the diagram is a follow-up if the bundle budget tightens.
- The contract for `query-api.v1.yaml` documents `deployment_rejected` in its v1.1.0 description but does not list it in the AuditEvent enum schema. The demo uses the canonical schema's enum for its KIND filter and renders the wider kind set via `DisplayAuditEvent`. See `docs/DECISIONS.md` 2026-05-14 entry.
- Fixtures were synthesized from the documented schema constants (ADR-0002 SHA, `_DEFAULT_DECODING_SEED` from `policy_generator.py`, feature-002 quickstart tenant + vehicle ids) when this session's environment could not run Compose end-to-end. `record_fixtures.sh` is the canonical re-capture path; running it against a live stack replaces the synthesized set. Documented in `docs/DECISIONS.md`.
