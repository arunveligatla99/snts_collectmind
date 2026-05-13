import { cn } from "@/lib/cn";

export interface SloTileProps {
  label: string;
  value: string;
  unit?: string;
  budget?: string;
  headroom?: string;
  source: string;
  status?: "pass" | "gated";
}

export function SloTile({ label, value, unit, budget, headroom, source, status = "pass" }: SloTileProps) {
  return (
    <div className="panel p-4 flex flex-col gap-1">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className="flex items-baseline gap-1">
        <div className="text-2xl font-semibold text-zinc-50">{value}</div>
        {unit ? <div className="text-sm text-zinc-400">{unit}</div> : null}
      </div>
      {budget ? (
        <div className="text-xs text-zinc-400">
          budget {budget}
          {headroom ? <span className="text-emerald-300 ml-2">{headroom}</span> : null}
        </div>
      ) : null}
      <div className="mt-auto flex items-center justify-between pt-2 text-[11px] text-zinc-500">
        <span>{source}</span>
        <span
          className={cn(
            status === "pass" ? "pill-ok" : "pill-warn",
          )}
        >
          {status === "pass" ? "PASS" : "gated"}
        </span>
      </div>
    </div>
  );
}
