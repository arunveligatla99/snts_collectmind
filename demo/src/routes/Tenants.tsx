import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  publishDiagnosticFinding,
  type AcceptedReceipt,
  type DiagnosticFindingEvent,
} from "@/api/endpoints/orchestration";
import { getAuditTrail, getOwnTenantConfig, getPolicyById } from "@/api/endpoints/query";
import { breakGlassAuditQuery } from "@/api/endpoints/audit-admin";
import { AuditChain, type DisplayAuditEvent, toDisplay } from "@/components/AuditChain";
import { TokenChip } from "@/components/TokenChip";
import { ApiError } from "@/api/client";
import type { AuditEvent, TenantConfig } from "@/api/endpoints/query";
import type { OperatorAuditEvent } from "@/api/endpoints/audit-admin";
import type { PrincipalKey } from "@/store/tokens";

type TenantId = "tenant-a" | "tenant-b";

interface TenantColumnState {
  principal: PrincipalKey;
  finding: DiagnosticFindingEvent;
  receipt: AcceptedReceipt | null;
}

const FINDING_A: DiagnosticFindingEvent = {
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

const FINDING_B: DiagnosticFindingEvent = {
  ...FINDING_A,
  finding_id: "f-tenant-b-001",
  hypothesis_statement: "Rear-right pad wear approaching threshold",
  vehicle_scope: ["VIN-BBBB-0001"],
  upstream_confidence: 0.79,
};

const POLICY_A_ID = "pol-tenant-a-brake-wear";

export function Tenants() {
  const [a, setA] = useState<TenantColumnState>({
    principal: "tenant-a",
    finding: FINDING_A,
    receipt: null,
  });
  const [b, setB] = useState<TenantColumnState>({
    principal: "tenant-b",
    finding: FINDING_B,
    receipt: null,
  });
  const [breakGlassReason, setBreakGlassReason] =
    useState<"incident_response" | "legal_hold" | "regulator_request" | "support_escalation" | "operator_self_audit">(
      "incident_response",
    );
  const [breakGlassResult, setBreakGlassResult] = useState<OperatorAuditEvent[] | null>(null);
  const [breakGlassError, setBreakGlassError] = useState<string | null>(null);

  const configA = useQuery({
    queryKey: ["tenant-config", "tenant-a"],
    queryFn: () => getOwnTenantConfig("tenant-a"),
  });
  const configB = useQuery({
    queryKey: ["tenant-config", "tenant-b"],
    queryFn: () => getOwnTenantConfig("tenant-b"),
  });

  const submitA = useMutation({
    mutationFn: () => publishDiagnosticFinding(a.finding, "tenant-a"),
    onSuccess: (r) => setA((s) => ({ ...s, receipt: r })),
  });
  const submitB = useMutation({
    mutationFn: () => publishDiagnosticFinding(b.finding, "tenant-b"),
    onSuccess: (r) => setB((s) => ({ ...s, receipt: r })),
  });

  const auditA = useQuery({
    enabled: Boolean(a.receipt),
    queryKey: ["audit", a.receipt?.correlation_id, "tenant-a"],
    queryFn: () => getAuditTrail(a.receipt!.correlation_id, "tenant-a"),
  });
  const auditB = useQuery({
    enabled: Boolean(b.receipt),
    queryKey: ["audit", b.receipt?.correlation_id, "tenant-b"],
    queryFn: () => getAuditTrail(b.receipt!.correlation_id, "tenant-b"),
  });

  const crossA = useQuery({
    enabled: Boolean(a.receipt),
    queryKey: ["cross-as-b", POLICY_A_ID],
    queryFn: async () => {
      try {
        await getPolicyById(POLICY_A_ID, "tenant-b");
        return { status: 200 as number, code: "OK" };
      } catch (e) {
        if (e instanceof ApiError) return { status: e.status, code: e.code };
        throw e;
      }
    },
  });

  const breakGlass = useMutation({
    mutationFn: () => {
      const cid = a.receipt?.correlation_id;
      if (!cid) throw new Error("Submit tenant-a finding first.");
      return breakGlassAuditQuery(
        {
          tenant_scope: "tenant-a",
          correlation_id: cid,
          reason_code: breakGlassReason,
        },
        "operator-alice",
      );
    },
    onSuccess: (r) => {
      setBreakGlassResult(r.events);
      setBreakGlassError(null);
    },
    onError: (e) => {
      setBreakGlassError(e instanceof ApiError ? `${e.status} · ${e.code}` : (e as Error).message);
      setBreakGlassResult(null);
    },
  });

  const breakGlassMerged = useMemo<DisplayAuditEvent[]>(() => {
    const tenantSide = (auditA.data ?? []).map(toDisplay);
    if (!breakGlassResult) return tenantSide;
    const seen = new Set<string>();
    const out: DisplayAuditEvent[] = [];
    const push = (evt: DisplayAuditEvent) => {
      if (!seen.has(evt.event_id)) {
        seen.add(evt.event_id);
        out.push(evt);
      }
    };
    tenantSide.forEach(push);
    breakGlassResult.map(toDisplay).forEach(push);
    return out.sort((x, y) => x.occurred_at.localeCompare(y.occurred_at));
  }, [auditA.data, breakGlassResult]);

  return (
    <div className="px-4 lg:px-8 py-6 space-y-6">
      <header className="space-y-1 max-w-6xl">
        <h1 className="text-2xl font-semibold text-zinc-50">Tenants — isolation + break-glass</h1>
        <p className="text-sm text-zinc-400">
          Two tenants enroll under distinct JWTs. Each owns one vehicle. Cross-tenant access of any
          shape collapses to <span className="font-mono">404</span> per FR-006; the operator surface
          has a separate audience and writes an immutable <span className="font-mono">kind=break_glass</span>{" "}
          row in the same transaction as the bypassed SELECT (ADR-0007).
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TenantColumn
          tenant="tenant-a"
          state={a}
          setState={setA}
          submit={() => submitA.mutate()}
          submitting={submitA.isPending}
          submitError={submitA.error}
          audit={auditA.data ?? []}
          fetchingAudit={auditA.isFetching}
          tenantConfig={configA.data}
          crossTenantResult={crossA.data}
          policyId={POLICY_A_ID}
        />

        <div className="panel">
          <div className="panel-header flex items-center justify-between">
            <span>Operator — break-glass</span>
            <TokenChip principal="operator-alice" audience="collectmind-operator" />
          </div>
          <div className="p-4 space-y-3">
            <p className="text-xs text-zinc-400">
              Distinct router · operator-audience JWT · service-principal connection bypasses RLS.
              Atomic <span className="font-mono">kind=break_glass</span> audit row written inside
              the same transaction as the bypassed SELECT (FR-005b).
            </p>
            <label className="text-xs text-zinc-400 flex flex-col gap-1">
              reason_code
              <select
                value={breakGlassReason}
                onChange={(e) =>
                  setBreakGlassReason(e.target.value as typeof breakGlassReason)
                }
                className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-1.5 text-sm text-zinc-100"
                aria-label="reason_code"
              >
                <option value="incident_response">incident_response</option>
                <option value="legal_hold">legal_hold</option>
                <option value="regulator_request">regulator_request</option>
                <option value="support_escalation">support_escalation</option>
                <option value="operator_self_audit">operator_self_audit</option>
              </select>
            </label>
            <div className="text-xs text-zinc-400">
              tenant_scope <span className="pill-neutral">tenant-a</span>
              <br />
              correlation_id{" "}
              <span className="font-mono text-zinc-200">{a.receipt?.correlation_id ?? "—"}</span>
            </div>
            <button
              type="button"
              className="btn-primary"
              disabled={!a.receipt || breakGlass.isPending}
              onClick={() => breakGlass.mutate()}
            >
              {breakGlass.isPending ? "Querying…" : "POST /audit/break-glass/query"}
            </button>
            {breakGlassError ? (
              <div className="pill-bad" role="alert">
                {breakGlassError}
              </div>
            ) : null}
            <div className="text-xs text-zinc-400 pt-2 border-t border-zinc-800">
              Merged audit chain for{" "}
              <span className="font-mono">{a.receipt?.correlation_id ?? "—"}</span> — tenant-a's
              chain + the operator's <span className="font-mono">break_glass</span> row.
            </div>
            <AuditChain
              events={breakGlassMerged}
              emptyHint="Submit tenant-a finding and run break-glass."
              highlightKinds={["break_glass", "vehicle_assignment_change"]}
            />
          </div>
        </div>

        <TenantColumn
          tenant="tenant-b"
          state={b}
          setState={setB}
          submit={() => submitB.mutate()}
          submitting={submitB.isPending}
          submitError={submitB.error}
          audit={auditB.data ?? []}
          fetchingAudit={auditB.isFetching}
          tenantConfig={configB.data}
          crossTenantResult={undefined}
          policyId={POLICY_A_ID}
        />
      </div>
    </div>
  );
}

interface TenantColumnProps {
  tenant: TenantId;
  state: TenantColumnState;
  setState: (next: TenantColumnState | ((s: TenantColumnState) => TenantColumnState)) => void;
  submit: () => void;
  submitting: boolean;
  submitError: unknown;
  audit: AuditEvent[];
  fetchingAudit: boolean;
  tenantConfig: TenantConfig | undefined;
  crossTenantResult: { status: number; code: string } | undefined;
  policyId: string;
}

function TenantColumn(props: TenantColumnProps) {
  const tone = props.tenant === "tenant-a" ? "accent" : "neutral";
  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between gap-2">
        <span className={tone === "accent" ? "text-accent-300" : "text-zinc-200"}>
          {props.tenant}
        </span>
        <TokenChip principal={props.state.principal} audience="collectmind-tenant" />
      </div>
      <div className="p-4 space-y-3">
        <div className="text-xs grid grid-cols-2 gap-x-3 gap-y-1">
          <span className="text-zinc-500">vehicle</span>
          <span className="font-mono text-zinc-200">{props.state.finding.vehicle_scope[0]}</span>
          <span className="text-zinc-500">inbound rate-limit</span>
          <span className="font-mono text-zinc-200">
            {props.tenantConfig
              ? `${props.tenantConfig.inbound.sustained_rps} rps / ${props.tenantConfig.inbound.burst_capacity} burst`
              : "—"}
          </span>
          <span className="text-zinc-500">config source</span>
          <span className="font-mono text-zinc-200">{props.tenantConfig?.source ?? "—"}</span>
        </div>
        <button
          type="button"
          className="btn-primary w-full"
          onClick={props.submit}
          disabled={props.submitting}
        >
          {props.submitting ? "Publishing…" : `POST /findings as ${props.tenant}`}
        </button>
        {props.submitError ? (
          <div className="pill-bad" role="alert">
            {props.submitError instanceof ApiError
              ? `${props.submitError.status} · ${props.submitError.code}`
              : (props.submitError as Error).message}
          </div>
        ) : null}
        {props.state.receipt ? (
          <div className="text-xs text-zinc-400">
            correlation_id{" "}
            <span className="font-mono text-zinc-200 break-all">
              {props.state.receipt.correlation_id}
            </span>
          </div>
        ) : null}
        <div>
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Audit chain</div>
          {props.fetchingAudit && props.audit.length === 0 ? (
            <div className="text-xs text-zinc-400">fetching…</div>
          ) : (
            <AuditChain
              events={props.audit}
              emptyHint="Submit to populate the chain."
              highlightKinds={["generated", "deployed", "outcome"]}
            />
          )}
        </div>
        <CrossTenantBlock tenant={props.tenant} result={props.crossTenantResult} policyId={props.policyId} />
      </div>
    </div>
  );
}

function CrossTenantBlock({
  tenant,
  result,
  policyId,
}: {
  tenant: TenantId;
  result: { status: number; code: string } | undefined;
  policyId: string;
}) {
  if (tenant !== "tenant-b") return null;
  return (
    <div className="border-t border-zinc-800 pt-3 space-y-1">
      <div className="text-[11px] uppercase tracking-wide text-zinc-500">Cross-tenant probe</div>
      <div className="text-xs text-zinc-400">
        GET <span className="font-mono">/policies/{policyId}</span> as tenant-b
      </div>
      <div className="text-xs">
        {result === undefined ? (
          <span className="pill-neutral">probing…</span>
        ) : result.status === 404 ? (
          <span className="pill-ok">
            HTTP {result.status} · {result.code} — FR-006 collapse
          </span>
        ) : (
          <span className="pill-bad">
            HTTP {result.status} · {result.code} — EXPECTED 404
          </span>
        )}
      </div>
    </div>
  );
}
