import { SloTile } from "@/components/SloTile";

const MEASURED = [
  {
    label: "Dashboard lag (SC-006)",
    value: "2.11",
    unit: "s",
    budget: "10 s",
    headroom: "~5×",
    source: "T136 max of 5 runs · runbook slo-006-dashboard-lag.md",
  },
  {
    label: "Dashboard lag mean (SC-006)",
    value: "1.98",
    unit: "s",
    budget: "10 s",
    headroom: "~5×",
    source: "T136 · 5-run mean",
  },
  {
    label: "Quickstart e2e (SC-008)",
    value: "27.32",
    unit: "s",
    budget: "600 s",
    headroom: "~22×",
    source: "T139 · feature 001 · warm Compose",
  },
  {
    label: "Quickstart e2e (SC-008)",
    value: "3",
    unit: "s",
    budget: "600 s",
    headroom: "~200×",
    source: "T292 · feature 002 · warm Compose",
  },
  {
    label: "Coverage (Principle IV)",
    value: "85.36",
    unit: "%",
    budget: "≥ 85 %",
    headroom: "+0.36 pp",
    source: "T285 across-tier · pytest-cov",
  },
  {
    label: "Coverage (feature 001 closure)",
    value: "86.24",
    unit: "%",
    budget: "≥ 85 %",
    headroom: "+1.24 pp",
    source: "T134 · feature 001",
  },
  {
    label: "CI wall-clock (SC-009)",
    value: "11m 02s",
    budget: "20 min",
    headroom: "9 min",
    source: "PR #1 · run-id 25775623611",
  },
  {
    label: "Smoke load p50",
    value: "50",
    unit: "ms",
    budget: "4 s",
    headroom: "~80×",
    source: "T134 · 280 reqs · 0 failures · 60 s",
  },
];

const GATED = [
  {
    label: "Sustained ingest (SC-002)",
    detail: "≥ 99.9 % success at 1000 ev/s/tenant for 30 min",
    gate: "workflow_dispatch · `.github/workflows/ci-workflow-dispatch.yaml`",
    enforced: "locustfile_full.py quitting hook",
  },
  {
    label: "24h soak (SC-003)",
    detail: "memory growth ≤ 5 % · error rate ≤ 0.1 %",
    gate: "nightly · `.github/workflows/nightly.yaml`",
    enforced: "SoakMemoryGrowthBreach + SoakErrorRateBreach + post-run RSS gate",
  },
  {
    label: "Query API p95 (SC-004)",
    detail: "≤ 200 ms at 100 reads/s",
    gate: "workflow_dispatch",
    enforced: "QueryLatencyBreach Prometheus rule",
  },
  {
    label: "ADR-0002 eval baseline",
    detail: "Qwen2.5-7B-Instruct VSS pass rate + p50 gen latency",
    gate: "GPU runner · `[self-hosted, gpu]` · eval-suite job",
    enforced: "Promotion blocker; deliberately bracketed (no-fabrication)",
  },
];

const TEST_TIER = [
  { tier: "Unit", count: "329", skip: "3 (named)" },
  { tier: "Contract", count: "17", skip: "0" },
  { tier: "Integration", count: "24", skip: "2 (named)" },
  { tier: "Migration rollback (isolated)", count: "2", skip: "0" },
];

export function Slo() {
  return (
    <div className="px-4 lg:px-8 py-6 space-y-8 max-w-6xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-zinc-50">SLOs — measured + gated</h1>
        <p className="text-sm text-zinc-400">
          Principle XI is non-negotiable: SLOs are measured, not aspired. Real local-run numbers
          below, plus the workflow_dispatch + nightly gating per Principle XIV. No fabrication —
          every value sources to a named artifact.
        </p>
      </header>

      <section>
        <h2 className="text-lg font-semibold text-zinc-100 mb-3">Measured (local runs)</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {MEASURED.map((m) => (
            <SloTile key={`${m.label}-${m.source}`} {...m} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-zinc-100 mb-3">Phase 14 test bar</h2>
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-zinc-400">
              <tr>
                <th className="px-4 py-2 font-medium">Tier</th>
                <th className="px-4 py-2 font-medium">Pass</th>
                <th className="px-4 py-2 font-medium">Skip</th>
              </tr>
            </thead>
            <tbody>
              {TEST_TIER.map((row) => (
                <tr key={row.tier} className="border-t border-zinc-800">
                  <td className="px-4 py-2 text-zinc-200">{row.tier}</td>
                  <td className="px-4 py-2 font-mono text-zinc-100">{row.count}</td>
                  <td className="px-4 py-2 font-mono text-zinc-400">{row.skip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-zinc-100 mb-3">
          Gated (workflow_dispatch · nightly · GPU runner)
        </h2>
        <p className="text-sm text-zinc-400 mb-3">
          Principle XIV gates full-SLM and full-load runs. Locally we measure what's locally
          measurable; the rest is enforced in CI workflows that don't run on every PR.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {GATED.map((g) => (
            <div key={g.label} className="panel p-4 space-y-1">
              <div className="flex items-center justify-between">
                <div className="font-medium text-zinc-100">{g.label}</div>
                <span className="pill-warn">gated</span>
              </div>
              <div className="text-sm text-zinc-300">{g.detail}</div>
              <div className="text-xs text-zinc-500">trigger: {g.gate}</div>
              <div className="text-xs text-zinc-500">enforcement: {g.enforced}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
