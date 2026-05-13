import { describe, it, expect, beforeEach } from "vitest";
import {
  publishDiagnosticFinding,
  submitErasureRequest,
} from "@/api/endpoints/orchestration";
import {
  getAuditTrail,
  getOutcomeForFinding,
  getOwnTenantConfig,
  getPolicyById,
} from "@/api/endpoints/query";
import { breakGlassAuditQuery } from "@/api/endpoints/audit-admin";
import { readyCheck } from "@/api/endpoints/health";
import { useModeStore } from "@/store/mode";
import { resetStores } from "./utils";

beforeEach(() => {
  resetStores();
  useModeStore.setState({ mode: "recorded" });
});

describe("endpoint thin wrappers route through the recorded client", () => {
  it("publishDiagnosticFinding returns an AcceptedReceipt", async () => {
    const r = await publishDiagnosticFinding(
      {
        schema_version: "1.0.0",
        finding_id: "f-tenant-a-001",
        anomaly_type: "brake_wear_early_stage",
        hypothesis_class: "BrakeWearHypothesisRule",
        hypothesis_statement: "Front-left pad wear approaching threshold",
        candidate_signals: ["Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear"],
        vehicle_scope: ["VIN-AAAA-0001"],
        upstream_confidence: 0.86,
      },
      "tenant-a",
    );
    expect(r.tenant_id).toBe("tenant-a");
    expect(r.correlation_id).toBeTruthy();
  });

  it("submitErasureRequest returns a receipt", async () => {
    const r = await submitErasureRequest(
      { subject_kind: "vehicle", subject_identifier: "VIN-AAAA-0001", mode: "erased" },
      "tenant-a",
    );
    expect(r.request_id).toBe("er-tenant-a-001");
    expect(r.target_completion_at).toBeTruthy();
  });

  it("getAuditTrail returns the chain", async () => {
    const events = await getAuditTrail("01HW1A2B3C4D5E6F7G8H9J0KQA", "tenant-a");
    expect(events.length).toBe(5);
    expect(events[0]?.kind).toBe("accepted");
  });

  it("getOutcomeForFinding returns the outcome", async () => {
    const o = await getOutcomeForFinding("f-tenant-a-001", "tenant-a");
    expect(o.hypothesis_state).toBe("confirmed");
  });

  it("getOwnTenantConfig returns the requesting tenant's config", async () => {
    const c = await getOwnTenantConfig("tenant-b");
    expect(c.source).toBe("override");
    expect(c.inbound.sustained_rps).toBe(50);
  });

  it("getPolicyById returns the policy for the owning tenant", async () => {
    const p = await getPolicyById("pol-tenant-a-brake-wear", "tenant-a");
    expect(p.version).toBe("1.0.0");
    expect(p.slm_repo).toBe("Qwen/Qwen2.5-7B-Instruct");
  });

  it("getPolicyById rejects with a 404 ApiError when cross-tenant", async () => {
    await expect(
      getPolicyById("pol-tenant-a-brake-wear", "tenant-b"),
    ).rejects.toMatchObject({ status: 404 });
  });

  it("breakGlassAuditQuery returns an event list", async () => {
    const r = await breakGlassAuditQuery(
      {
        tenant_scope: "tenant-a",
        correlation_id: "01HW1A2B3C4D5E6F7G8H9J0KQA",
        reason_code: "incident_response",
      },
      "operator-alice",
    );
    expect(r.total).toBe(6);
    expect(r.events.some((e) => e.kind === "break_glass")).toBe(true);
  });

  it("readyCheck returns ok in recorded mode (via the /ready fixture)", async () => {
    const r = await readyCheck();
    expect(r).toBe("ok");
  });
});
