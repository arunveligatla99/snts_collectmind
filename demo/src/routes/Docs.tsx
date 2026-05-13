import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { renderMarkdown } from "@/lib/markdown";
import manifest from "@/content/manifest.json";

import constitutionSrc from "@/content/constitution.md?raw";
import f1Src from "@/content/feature-001-readiness-review.md?raw";
import f2Src from "@/content/feature-002-readiness-review.md?raw";
import adrIndexSrc from "@/content/adrs/README.md?raw";
import adr1Src from "@/content/adrs/0001-pin-covesa-vss.md?raw";
import adr2Src from "@/content/adrs/0002-default-slm-qwen2-5-7b-instruct.md?raw";
import adr3Src from "@/content/adrs/0003-constrained-decoding-library.md?raw";
import adr4Src from "@/content/adrs/0004-fingerprint-stub.md?raw";
import adr5Src from "@/content/adrs/0005-slm-hosting-topology.md?raw";
import adr6Src from "@/content/adrs/0006-dev-default-policy-client.md?raw";
import adr7Src from "@/content/adrs/0007-rls-restrictive-and-break-glass.md?raw";
import adr8Src from "@/content/adrs/0008-per-tenant-rate-limiting.md?raw";
import adr9Src from "@/content/adrs/0009-tenant-vehicle-ownership-store.md?raw";

interface DocEntry {
  slug: string;
  title: string;
  src: string;
}

const DOCS: DocEntry[] = [
  { slug: "constitution", title: "Constitution v1.0.1", src: constitutionSrc },
  { slug: "feature-001-readiness-review", title: "Feature 001 — readiness review", src: f1Src },
  { slug: "feature-002-readiness-review", title: "Feature 002 — readiness review", src: f2Src },
  { slug: "adr-index", title: "ADR index", src: adrIndexSrc },
  { slug: "adr-0001", title: "ADR-0001 · Pin COVESA VSS", src: adr1Src },
  { slug: "adr-0002", title: "ADR-0002 · Default SLM (Qwen2.5-7B-Instruct)", src: adr2Src },
  { slug: "adr-0003", title: "ADR-0003 · Constrained-decoding library", src: adr3Src },
  { slug: "adr-0004", title: "ADR-0004 · Deterministic-fingerprint stub", src: adr4Src },
  { slug: "adr-0005", title: "ADR-0005 · SLM hosting topology", src: adr5Src },
  { slug: "adr-0006", title: "ADR-0006 · DevDefaultPolicyClient", src: adr6Src },
  { slug: "adr-0007", title: "ADR-0007 · RESTRICTIVE RLS + break-glass", src: adr7Src },
  { slug: "adr-0008", title: "ADR-0008 · Per-tenant rate limiting", src: adr8Src },
  { slug: "adr-0009", title: "ADR-0009 · Tenant-vehicle ownership store", src: adr9Src },
];

export function Docs() {
  return (
    <div className="px-4 lg:px-8 py-6 grid grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)] gap-6 max-w-6xl">
      <aside className="space-y-1 lg:sticky lg:top-24 self-start">
        <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Snapshot</div>
        <div className="text-xs text-zinc-400 mb-3">
          git <span className="font-mono">{manifest.sha}</span> · {manifest.date}
        </div>
        {DOCS.map((d) => (
          <NavLink
            key={d.slug}
            to={d.slug}
            className={({ isActive }) =>
              `block text-sm rounded px-2 py-1 ${
                isActive ? "bg-accent-500/15 text-accent-200" : "text-zinc-300 hover:bg-zinc-900"
              }`
            }
          >
            {d.title}
          </NavLink>
        ))}
      </aside>
      <Routes>
        <Route index element={<DocViewer entry={DOCS[0]!} />} />
        <Route path=":slug" element={<DocParamViewer />} />
      </Routes>
    </div>
  );
}

function DocParamViewer() {
  const params = useParams();
  const entry = DOCS.find((d) => d.slug === params.slug);
  if (!entry) {
    return <div className="prose-doc">Not found.</div>;
  }
  return <DocViewer entry={entry} />;
}

function DocViewer({ entry }: { entry: DocEntry }) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    setHtml(renderMarkdown(entry.src));
  }, [entry]);
  return (
    <article className="prose-doc max-w-none" dangerouslySetInnerHTML={{ __html: html }} />
  );
}
