import type { components } from "../types/audit-admin";
import { apiCall } from "../client";
import type { PrincipalKey } from "@/store/tokens";

export type BreakGlassRequest = components["schemas"]["BreakGlassRequest"];
export type AuditEventList = components["schemas"]["AuditEventList"];
export type OperatorAuditEvent = components["schemas"]["AuditEvent"];

export function breakGlassAuditQuery(
  body: BreakGlassRequest,
  principal: PrincipalKey,
): Promise<AuditEventList> {
  return apiCall<AuditEventList>({
    method: "POST",
    path: "/audit/break-glass/query",
    principal,
    body,
  });
}
