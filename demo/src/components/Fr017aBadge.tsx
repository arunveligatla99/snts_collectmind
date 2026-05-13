import type { DisplayAuditEvent } from "./AuditChain";

interface Props {
  event: DisplayAuditEvent;
}

export function Fr017aBadge({ event }: Props) {
  const fields: Array<[string, string | undefined]> = [
    ["slm_repo", event.slm_repo],
    ["slm_revision_sha", event.slm_revision_sha],
    ["slm_runtime", event.slm_runtime],
    ["slm_runtime_version", event.slm_runtime_version],
    ["slm_quantization", event.slm_quantization],
    [
      "slm_decoding_seed",
      event.slm_decoding_seed !== undefined ? String(event.slm_decoding_seed) : undefined,
    ],
    ["prompt_template_version", event.prompt_template_version],
  ];
  const present = fields.filter(([, v]) => v !== undefined && v !== "");
  if (present.length === 0) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
      {present.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <span className="text-zinc-500 shrink-0 w-44">{k}</span>
          <span className="font-mono text-zinc-200 break-all">{v}</span>
        </div>
      ))}
    </div>
  );
}
