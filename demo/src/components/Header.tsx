import { useEffect, useState } from "react";
import { useModeStore } from "@/store/mode";
import { ModeToggle } from "./ModeToggle";
import { ThemeToggle } from "./ThemeToggle";

export function Header() {
  const mode = useModeStore((s) => s.mode);
  const [now, setNow] = useState<string>(() => new Date().toISOString().slice(0, 10));
  useEffect(() => {
    const id = setInterval(() => setNow(new Date().toISOString().slice(0, 10)), 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
      <div className="px-4 py-2.5 flex items-center gap-4">
        <a href={import.meta.env.BASE_URL} className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-md bg-accent-500 grid place-items-center text-white font-bold">
            ◆
          </div>
          <div>
            <div className="font-semibold tracking-tight">CollectMind</div>
            <div className="text-[11px] text-zinc-400 -mt-0.5">
              Agentic vehicle-telemetry policy engine
            </div>
          </div>
        </a>
        <div className="hidden lg:flex items-center gap-2 ml-2">
          <span className="pill-neutral">SLM-first</span>
          <span className="pill-neutral">deterministic CI</span>
          <span className="pill-neutral">multi-tenant RLS</span>
          <span className="pill-accent">audit chain</span>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="text-zinc-500 hidden sm:inline">{now}</span>
          <ModeToggle />
          <ThemeToggle />
          <a
            href="https://github.com/arunveligatla99/snts_collectmind"
            target="_blank"
            rel="noreferrer noopener"
            className="btn-secondary"
            aria-label="Open repository on GitHub"
          >
            GitHub ↗
          </a>
        </div>
      </div>
      {mode === "recorded" ? <RecordedBanner /> : null}
    </header>
  );
}

function RecordedBanner() {
  const sha = import.meta.env.VITE_SNAPSHOT_SHA ?? "local";
  const date = import.meta.env.VITE_SNAPSHOT_DATE ?? "2026-05-13";
  return (
    <div className="px-4 py-1.5 text-[11px] border-t border-zinc-800 bg-accent-500/10 text-accent-100 flex flex-wrap gap-x-3 gap-y-1">
      <span className="font-medium">Recorded snapshot</span>
      <span className="text-zinc-300">
        captured {date} · git <span className="font-mono">{sha}</span>
      </span>
      <span className="text-zinc-400">
        Deployed-only mode. Live mode runs locally against the Compose stack.
      </span>
    </div>
  );
}
