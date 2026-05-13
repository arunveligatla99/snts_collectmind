import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    primaryColor: "#1e1b4b",
    primaryTextColor: "#ede9fe",
    primaryBorderColor: "#8b5cf6",
    lineColor: "#a78bfa",
    fontFamily: "Inter, sans-serif",
  },
  flowchart: { curve: "basis" },
});

interface Props {
  chart: string;
  caption?: string;
}

let idCounter = 0;

export function MermaidDiagram({ chart, caption }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    idCounter += 1;
    const id = `mmd-${idCounter}`;
    let cancelled = false;
    mermaid
      .render(id, chart)
      .then(({ svg }) => {
        if (!cancelled && el) {
          el.innerHTML = svg;
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (error) {
    return (
      <div className="code-block text-rose-300" data-testid="mermaid-error">
        Mermaid render error: {error}
      </div>
    );
  }
  return (
    <figure>
      <div
        ref={ref}
        role="img"
        aria-label={caption ?? "Architecture diagram"}
        className="panel p-4 overflow-x-auto [&_svg]:mx-auto"
        data-testid="mermaid-host"
      />
      {caption ? (
        <figcaption className="text-xs text-zinc-500 mt-2 text-center">{caption}</figcaption>
      ) : null}
    </figure>
  );
}
