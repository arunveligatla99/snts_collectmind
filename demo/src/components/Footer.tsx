import { ConnectivityDot } from "./ConnectivityDot";

export function Footer() {
  const sha = import.meta.env.VITE_SNAPSHOT_SHA ?? "local";
  const date = import.meta.env.VITE_SNAPSHOT_DATE ?? "2026-05-13";
  return (
    <footer className="border-t border-zinc-800 bg-zinc-950/60 px-4 py-2 text-[11px] text-zinc-400 flex flex-wrap items-center gap-x-4 gap-y-1">
      <ConnectivityDot />
      <span>
        Snapshot <span className="font-mono">{sha}</span> · {date}
      </span>
      <span className="text-zinc-500">OpenAPI v1.1.0</span>
      <span className="ml-auto text-zinc-500">
        © 2026 CollectMind — built per constitution v1.0.1
      </span>
    </footer>
  );
}
