import { useModeStore } from "@/store/mode";

export function ModeToggle() {
  const mode = useModeStore((s) => s.mode);
  const setMode = useModeStore((s) => s.setMode);
  const next = mode === "live" ? "recorded" : "live";
  return (
    <button
      type="button"
      onClick={() => setMode(next)}
      className="btn-secondary"
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      <span className={mode === "live" ? "text-emerald-400" : "text-accent-300"}>●</span>
      <span className="hidden sm:inline">mode:</span>
      <span className="font-medium">{mode}</span>
    </button>
  );
}
