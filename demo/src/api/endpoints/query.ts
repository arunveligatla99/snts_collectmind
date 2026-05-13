import type { components } from "../types/query";
import { apiCall } from "../client";
import type { PrincipalKey } from "@/store/tokens";

export type CollectionPolicySpec = components["schemas"]["CollectionPolicySpec"];
export type PolicyOutcome = components["schemas"]["PolicyOutcome"];
export type AuditEvent = components["schemas"]["AuditEvent"];

export function getPolicyById(
  policyId: string,
  principal: PrincipalKey,
): Promise<CollectionPolicySpec> {
  return apiCall<CollectionPolicySpec>({
    method: "GET",
    path: `/policies/${policyId}`,
    principal,
  });
}

export function getOutcomeForFinding(
  findingId: string,
  principal: PrincipalKey,
): Promise<PolicyOutcome> {
  return apiCall<PolicyOutcome>({
    method: "GET",
    path: `/findings/${findingId}/outcome`,
    principal,
  });
}

export function getAuditTrail(
  correlationId: string,
  principal: PrincipalKey,
): Promise<AuditEvent[]> {
  return apiCall<AuditEvent[]>({
    method: "GET",
    path: `/audit/${correlationId}`,
    principal,
  });
}

export interface TenantConfig {
  tenant_id: string;
  inbound: { sustained_rps: number; burst_capacity: number };
  query: { sustained_rps: number; burst_capacity: number };
  source: "default" | "override";
  updated_at?: string;
}

export function getOwnTenantConfig(principal: PrincipalKey): Promise<TenantConfig> {
  return apiCall<TenantConfig>({
    method: "GET",
    path: "/tenant-config/self",
    principal,
  });
}
