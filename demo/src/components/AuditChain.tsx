import { useState } from "react";
import type { AuditEvent } from "@/api/endpoints/query";
import type { OperatorAuditEvent } from "@/api/endpoints/audit-admin";
import { Fr017aBadge } from "./Fr017aBadge";
import { cn } from "@/lib/cn";

export type DisplayAuditKind =
  | "accepted"
  | "generated"
  | "validated"
  | "deployed"
  | "outcome"
  | "rejected"
  | "erasure"
  | "break_glass"
  | "tenant_config_change"
  | "deployment_rejected"
  | "vehicle_assignment_change";

export interface DisplayAuditEvent {
  event_id: string;
  kind: DisplayAuditKind | string;
  occurred_at: string;
  correlation_id: string;
  principal_subject?: string;
  slm_repo?: string;
  slm_revision_sha?: string;
  slm_runtime?: string;
  slm_runtime_version?: string;
  slm_quantization?: string;
  slm_decoding_seed?: number;
  prompt_template_version?: string;
  inbound_schema_version?: string;
  time_acceleration_factor?: number;
  policy_ref?: Record<string, unknown>;
  deployment_ref?: Record<string, unknown>;
  outcome_ref?: Record<string, unknown>;
  extras?: Record<string, unknown>;
  tenant_id?: string;
}

export function toDisplay(evt: AuditEvent | OperatorAuditEvent): DisplayAuditEvent {
  const extras = (evt as { extras?: Record<string, unknown> }).extras;
  const flat: Record<string, unknown> = extras ?? {};
  return {
    event_id: evt.event_id,
    kind: evt.kind,
    occurred_at: evt.occurred_at,
    correlation_id: evt.correlation_id,
    principal_subject:
      (evt as { principal_subject?: string }).principal_subject ??
      (typeof flat["operator_principal_subject"] === "string"
        ? (flat["operator_principal_subject"] as string)
        : typeof flat["service_principal_subject"] === "string"
        ? (flat["service_principal_subject"] as string)
        : undefined),
    slm_repo: (evt as { slm_repo?: string }).slm_repo ?? (typeof flat["slm_repo"] === "string" ? (flat["slm_repo"] as string) : undefined),
    slm_revision_sha:
      (evt as { slm_revision_sha?: string }).slm_revision_sha ??
      (typeof flat["slm_revision_sha"] === "string" ? (flat["slm_revision_sha"] as string) : undefined),
    slm_runtime: (evt as { slm_runtime?: string }).slm_runtime,
    slm_runtime_version: (evt as { slm_runtime_version?: string }).slm_runtime_version,
    slm_quantization: (evt as { slm_quantization?: string }).slm_quantization,
    slm_decoding_seed:
      (evt as { slm_decoding_seed?: number }).slm_decoding_seed ??
      (typeof flat["slm_decoding_seed"] === "number" ? (flat["slm_decoding_seed"] as number) : undefined),
    prompt_template_version:
      (evt as { prompt_template_version?: string }).prompt_template_version ??
      (typeof flat["prompt_template_version"] === "string"
        ? (flat["prompt_template_version"] as string)
        : undefined),
    inbound_schema_version: (evt as { inbound_schema_version?: string }).inbound_schema_version,
    time_acceleration_factor: (evt as { time_acceleration_factor?: number }).time_acceleration_factor,
    policy_ref:
      (evt as { policy_ref?: Record<string, unknown> }).policy_ref ??
      (typeof flat["policy_ref"] === "object" && flat["policy_ref"] !== null
        ? (flat["policy_ref"] as Record<string, unknown>)
        : undefined),
    deployment_ref: (evt as { deployment_ref?: Record<string, unknown> }).deployment_ref,
    outcome_ref: (evt as { outcome_ref?: Record<string, unknown> }).outcome_ref,
    extras,
    tenant_id: (evt as { tenant_id?: string }).tenant_id,
  };
}

interface Props {
  events: ReadonlyArray<AuditEvent | OperatorAuditEvent | DisplayAuditEvent>;
  emptyHint?: string;
  highlightKinds?: ReadonlyArray<DisplayAuditKind>;
}

const KIND_LABELS: Record<string, string> = {
  accepted: "accepted",
  generated: "generated",
  validated: "validated",
  deployed: "deployed",
  outcome: "outcome",
  rejected: "rejected",
  erasure: "erasure",
  break_glass: "break-glass",
  tenant_config_change: "tenant-config-change",
  deployment_rejected: "deployment-rejected",
  vehicle_assignment_change: "vehicle-assignment-change",
};

function pillForKind(kind: string): string {
  if (kind === "rejected" || kind === "deployment_rejected") return "pill-bad";
  if (kind === "break_glass" || kind === "erasure") return "pill-warn";
  if (kind === "outcome" || kind === "deployed") return "pill-ok";
  return "pill-accent";
}

function relativeTime(base: string, current: string): string {
  const b = new Date(base).getTime();
  const c = new Date(current).getTime();
  if (Number.isNaN(b) || Number.isNaN(c)) return "";
  const delta = c - b;
  if (delta < 0) return `${(delta / 1000).toFixed(2)} s`;
  if (delta < 1000) return `+${delta} ms`;
  return `+${(delta / 1000).toFixed(2)} s`;
}

export function AuditChain({ events, emptyHint, highlightKinds }: Props) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(0);
  if (events.length === 0) {
    return (
      <div className="panel p-6 text-sm text-zinc-400 text-center">
        {emptyHint ?? "No audit events yet."}
      </div>
    );
  }
  const display: DisplayAuditEvent[] = events.map((e) =>
    "principal_subject" in e || "extras" in e ? toDisplay(e as AuditEvent | OperatorAuditEvent) : (e as DisplayAuditEvent),
  );
  const baseTs = display[0]?.occurred_at ?? "";
  const highlightSet = new Set<string>(highlightKinds ?? []);
  return (
    <ol className="space-y-2">
      {display.map((evt, idx) => {
        const isExpanded = expandedIdx === idx;
        const isHighlight = highlightSet.has(evt.kind);
        return (
          <li
            key={evt.event_id}
            className={cn(
              "panel transition",
              isHighlight && "ring-1 ring-accent-500/40",
            )}
          >
            <button
              type="button"
              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left"
              aria-expanded={isExpanded}
              aria-label={`Toggle event ${evt.event_id}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className={pillForKind(evt.kind)}>{KIND_LABELS[evt.kind] ?? evt.kind}</span>
                <span className="text-xs font-mono text-zinc-400 truncate">
                  {evt.event_id}
                </span>
              </div>
              <div className="flex items-center gap-3 shrink-0 text-xs text-zinc-400">
                <span>{relativeTime(baseTs, evt.occurred_at)}</span>
                <span aria-hidden="true">{isExpanded ? "▾" : "▸"}</span>
              </div>
            </button>
            {isExpanded ? (
              <div className="px-4 pb-4 space-y-3 border-t border-zinc-800">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs pt-3">
                  <div className="flex gap-2">
                    <span className="text-zinc-500 w-44">occurred_at</span>
                    <span className="font-mono text-zinc-200">{evt.occurred_at}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-zinc-500 w-44">correlation_id</span>
                    <span className="font-mono text-zinc-200 break-all">
                      {evt.correlation_id}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-zinc-500 w-44">principal_subject</span>
                    <span className="font-mono text-zinc-200 break-all">
                      {evt.principal_subject}
                    </span>
                  </div>
                </div>
                <Fr017aBadge event={evt} />
                <RefBlock label="policy_ref" value={evt.policy_ref} />
                <RefBlock label="deployment_ref" value={evt.deployment_ref} />
                <RefBlock label="outcome_ref" value={evt.outcome_ref} />
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function RefBlock({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null) return null;
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">{label}</div>
      <pre className="code-block">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
