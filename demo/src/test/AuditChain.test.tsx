import { describe, it, expect, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { AuditChain, toDisplay, type DisplayAuditEvent } from "@/components/AuditChain";
import { renderWithProviders, resetStores } from "./utils";

const SAMPLE: DisplayAuditEvent[] = [
  {
    event_id: "e-1",
    kind: "accepted",
    occurred_at: "2026-05-13T12:00:00.000Z",
    correlation_id: "cid-x",
    principal_subject: "tenant-a/clients/demo",
    inbound_schema_version: "1.0.0",
  },
  {
    event_id: "e-2",
    kind: "generated",
    occurred_at: "2026-05-13T12:00:01.347Z",
    correlation_id: "cid-x",
    principal_subject: "graph/policy-generator",
    slm_repo: "Qwen/Qwen2.5-7B-Instruct",
    slm_revision_sha: "a09a35458c702b33eeacc393d103063234e8bc28",
    slm_decoding_seed: 12648430,
    prompt_template_version: "1.0.0",
    policy_ref: { tenant_id: "tenant-a", policy_id: "pol-1", version: "1.0.0" },
  },
  {
    event_id: "e-3",
    kind: "deployment_rejected",
    occurred_at: "2026-05-13T12:00:02.000Z",
    correlation_id: "cid-x",
  },
];

describe("AuditChain", () => {
  beforeEach(resetStores);

  it("renders the empty hint when no events", () => {
    renderWithProviders(<AuditChain events={[]} emptyHint="Empty here." />);
    expect(screen.getByText("Empty here.")).toBeInTheDocument();
  });

  it("renders each kind label", () => {
    renderWithProviders(<AuditChain events={SAMPLE} />);
    expect(screen.getByText("accepted")).toBeInTheDocument();
    expect(screen.getByText("generated")).toBeInTheDocument();
    expect(screen.getByText("deployment-rejected")).toBeInTheDocument();
  });

  it("computes relative timestamps from the first event", () => {
    renderWithProviders(<AuditChain events={SAMPLE} />);
    expect(screen.getByText("+0 ms")).toBeInTheDocument();
    expect(screen.getByText("+1.35 s")).toBeInTheDocument();
  });

  it("expands an event to reveal FR-017a fields and refs", () => {
    renderWithProviders(<AuditChain events={SAMPLE} />);
    // generated is at index 1; clicking its toggle reveals its policy_ref
    const generatedBtn = screen.getByRole("button", { name: /Toggle event e-2/ });
    fireEvent.click(generatedBtn);
    expect(
      screen.getByText("a09a35458c702b33eeacc393d103063234e8bc28"),
    ).toBeInTheDocument();
    expect(screen.getByText("12648430")).toBeInTheDocument();
    expect(screen.getByText("policy_ref")).toBeInTheDocument();
  });

  it("collapses an expanded event when clicked again", () => {
    renderWithProviders(<AuditChain events={SAMPLE} />);
    const acceptedBtn = screen.getByRole("button", { name: /Toggle event e-1/ });
    // accepted starts expanded by default (index 0)
    expect(acceptedBtn).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(acceptedBtn);
    expect(acceptedBtn).toHaveAttribute("aria-expanded", "false");
  });

  it("highlights events in highlightKinds with the accent ring", () => {
    const { container } = renderWithProviders(
      <AuditChain events={SAMPLE} highlightKinds={["generated"]} />,
    );
    const rings = container.querySelectorAll(".ring-accent-500\\/40");
    expect(rings.length).toBe(1);
  });

  it("toDisplay flattens operator-side audit events to the display shape", () => {
    const opEvt = {
      event_id: "op-1",
      tenant_id: "tenant-a",
      kind: "break_glass" as const,
      correlation_id: "cid-x",
      occurred_at: "2026-05-13T12:01:00.000Z",
      // OpenAPI's `extras` schema is open per the per-kind field set in the
      // description; cast via `as never` to bypass the generated empty-record
      // narrowing in the typed test surface.
      extras: {
        operator_principal_subject: "operator-alice",
        tenant_scope: "tenant-a",
        reason_code: "incident_response",
        correlation_id: "cid-x",
      } as never,
    };
    const display = toDisplay(opEvt);
    expect(display.principal_subject).toBe("operator-alice");
    expect(display.tenant_id).toBe("tenant-a");
    expect(display.kind).toBe("break_glass");
  });
});
