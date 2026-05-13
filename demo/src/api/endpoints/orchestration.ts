import type { components } from "../types/orchestration";
import { apiCall } from "../client";
import type { PrincipalKey } from "@/store/tokens";

export type DiagnosticFindingEvent = components["schemas"]["DiagnosticFindingEvent"];
export type AcceptedReceipt = components["schemas"]["AcceptedReceipt"];
export type ErasureRequest = components["schemas"]["ErasureRequest"];
export type ErasureReceipt = components["schemas"]["ErasureReceipt"];

export function publishDiagnosticFinding(
  finding: DiagnosticFindingEvent,
  principal: PrincipalKey,
): Promise<AcceptedReceipt> {
  return apiCall<AcceptedReceipt>({
    method: "POST",
    path: "/findings",
    principal,
    body: finding,
  });
}

export function submitErasureRequest(
  request: ErasureRequest,
  principal: PrincipalKey,
): Promise<ErasureReceipt> {
  return apiCall<ErasureReceipt>({
    method: "POST",
    path: "/erasure-requests",
    principal,
    body: request,
  });
}
