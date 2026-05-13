import { useEffect } from "react";
import { useModeStore } from "@/store/mode";
import { readyCheck } from "@/api/endpoints/health";

export function ConnectivityDot() {
  const mode = useModeStore((s) => s.mode);
  const baseUrl = useModeStore((s) => s.baseUrl);
  const connectivity = useModeStore((s) => s.connectivity);
  const setConnectivity = useModeStore((s) => s.setConnectivity);

  useEffect(() => {
    if (mode === "recorded") {
      setConnectivity("ok");
      return;
    }
    let cancelled = false;
    const tick = async () => {
      const r = await readyCheck();
      if (!cancelled) setConnectivity(r);
    };
    void tick();
    const id = setInterval(tick, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [mode, baseUrl, setConnectivity]);

  const label =
    mode === "recorded"
      ? "recorded fixtures"
      : connectivity === "ok"
      ? "live · /ready 200"
      : connectivity === "down"
      ? "live · /ready unreachable"
      : "live · probing…";
  const tone =
    connectivity === "ok" ? "pill-ok" : connectivity === "down" ? "pill-bad" : "pill-warn";

  return (
    <span className={tone} role="status" aria-live="polite">
      ●&nbsp;{label}
    </span>
  );
}
