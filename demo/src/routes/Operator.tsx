import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  publishDiagnosticFinding,
  type AcceptedReceipt,
  type DiagnosticFindingEvent,
} from "@/api/endpoints/orchestration";
import { getAuditTrail, getOutcomeForFinding } from "@/api/endpoints/query";
import { AuditChain } from "@/components/AuditChain";
import { TokenChip } from "@/components/TokenChip";
import { ApiError } from "@/api/client";
import { Link } from "react-router-dom";

const DEFAULT_FINDING: DiagnosticFindingEvent = {
  schema_version: "1.0.0",
  finding_id: "f-tenant-a-001",
  anomaly_type: "brake_wear_early_stage",
  hypothesis_class: "BrakeWearHypothesisRule",
  hypothesis_statement: "Front-left pad wear approaching threshold",
  candidate_signals: [
    "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
    "Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature",
  ],
  vehicle_scope: ["VIN-AAAA-0001"],
  upstream_confidence: 0.86,
};

export function Operator() {
  const [editorText, setEditorText] = useState(() =>
    JSON.stringify(DEFAULT_FINDING, null, 2),
  );
  const [receipt, setReceipt] = useState<AcceptedReceipt | null>(null);

  const findingDraft = useMemo(() => {
    try {
      return { ok: true as const, value: JSON.parse(editorText) as DiagnosticFindingEvent };
    } catch (e) {
      return { ok: false as const, error: e instanceof Error ? e.message : String(e) };
    }
  }, [editorText]);

  const publish = useMutation({
    mutationFn: () => {
      if (!findingDraft.ok) throw new Error(findingDraft.error);
      return publishDiagnosticFinding(findingDraft.value, "tenant-a");
    },
    onSuccess: (r) => setReceipt(r),
  });

  const correlationId = receipt?.correlation_id;
  const audit = useQuery({
    enabled: Boolean(correlationId),
    queryKey: ["audit", correlationId],
    queryFn: () => getAuditTrail(correlationId!, "tenant-a"),
  });
  const outcome = useQuery({
    enabled: Boolean(receipt?.finding_id),
    queryKey: ["outcome", receipt?.finding_id],
    queryFn: () => getOutcomeForFinding(receipt!.finding_id, "tenant-a"),
  });

  return (
    <div className="px-4 lg:px-8 py-6 space-y-6 max-w-6xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-zinc-50">Operator — submit + watch the loop</h1>
        <p className="text-sm text-zinc-400">
          POST <span className="font-mono">/findings</span> as tenant-a, then poll the audit chain
          and the outcome. Every <span className="font-mono">generated</span> row carries the FR-017a
          minimum field set (SLM repo, revision SHA, prompt template, decoding seed, policy ref).
        </p>
      </header>

      <div className="panel">
        <div className="panel-header flex items-center justify-between gap-2">
          <span>Finding draft</span>
          <TokenChip principal="tenant-a" audience="collectmind-tenant" />
        </div>
        <div className="p-4 space-y-3">
          <textarea
            value={editorText}
            onChange={(e) => setEditorText(e.target.value)}
            spellCheck={false}
            rows={16}
            className="w-full font-mono text-xs bg-zinc-950 border border-zinc-800 rounded-md p-3 text-zinc-100 focus:outline-none focus:ring-1 focus:ring-accent-500"
            aria-label="DiagnosticFindingEvent JSON editor"
          />
          {findingDraft.ok ? null : (
            <div className="pill-bad" role="alert">
              JSON parse error: {findingDraft.error}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn-primary"
              disabled={!findingDraft.ok || publish.isPending}
              onClick={() => publish.mutate()}
            >
              {publish.isPending ? "Publishing…" : "POST /findings"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setEditorText(JSON.stringify(DEFAULT_FINDING, null, 2));
                setReceipt(null);
              }}
            >
              Reset
            </button>
            {publish.error ? (
              <span className="pill-bad" role="alert">
                {publish.error instanceof ApiError
                  ? `${publish.error.status} · ${publish.error.code}`
                  : publish.error.message}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {receipt ? (
        <div className="panel">
          <div className="panel-header">Receipt (HTTP 202)</div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <KV label="tenant_id" value={receipt.tenant_id} />
            <KV label="finding_id" value={receipt.finding_id} />
            <KV label="correlation_id" value={receipt.correlation_id} mono />
            <KV label="accepted_at" value={receipt.accepted_at} />
            <KV label="idempotent_replay" value={String(Boolean(receipt.idempotent_replay))} />
          </div>
          <div className="px-4 pb-4">
            <Link to={`/audit?cid=${receipt.correlation_id}`} className="btn-secondary">
              Open in /audit explorer →
            </Link>
          </div>
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-header">Audit chain</div>
        <div className="p-4">
          <AuditChain
            events={audit.data ?? []}
            emptyHint="Submit a finding above to populate the chain."
            highlightKinds={["generated", "deployed", "outcome"]}
          />
        </div>
      </div>

      {outcome.data ? (
        <div className="panel">
          <div className="panel-header">Outcome</div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <KV label="hypothesis_state" value={outcome.data.hypothesis_state} />
            <KV label="data_quality_score" value={String(outcome.data.data_quality_score)} />
            <KV
              label="signals_collected_count"
              value={String(outcome.data.signals_collected_count)}
            />
            <KV label="evaluated_at" value={outcome.data.evaluated_at} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function KV({ label, value, mono = false }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div className="flex gap-2">
      <span className="text-zinc-500 w-44 shrink-0">{label}</span>
      <span className={mono ? "font-mono text-zinc-200 break-all" : "text-zinc-200"}>
        {value ?? "—"}
      </span>
    </div>
  );
}
