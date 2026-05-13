import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getAuditTrail, type AuditEvent } from "@/api/endpoints/query";
import { AuditChain } from "@/components/AuditChain";
import { ApiError } from "@/api/client";

const DEFAULT_CID = "01HW1A2B3C4D5E6F7G8H9J0KQA";
const KIND_OPTIONS: ReadonlyArray<AuditEvent["kind"]> = [
  "accepted",
  "generated",
  "validated",
  "deployed",
  "outcome",
  "rejected",
  "erasure",
];

export function Audit() {
  const [params, setParams] = useSearchParams();
  const initialCid = params.get("cid") ?? DEFAULT_CID;
  const [cidInput, setCidInput] = useState(initialCid);
  const [cid, setCid] = useState(initialCid);
  const [filter, setFilter] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("");

  useEffect(() => {
    const fromUrl = params.get("cid");
    if (fromUrl && fromUrl !== cid) {
      setCid(fromUrl);
      setCidInput(fromUrl);
    }
  }, [params, cid]);

  const audit = useQuery({
    queryKey: ["audit", cid, "tenant-a"],
    queryFn: () => getAuditTrail(cid, "tenant-a"),
  });

  const visible = (audit.data ?? []).filter((evt) => {
    if (kindFilter && evt.kind !== kindFilter) return false;
    if (filter) {
      const hay = JSON.stringify(evt).toLowerCase();
      if (!hay.includes(filter.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div className="px-4 lg:px-8 py-6 space-y-6 max-w-6xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-zinc-50">Audit chain explorer</h1>
        <p className="text-sm text-zinc-400">
          Query the immutable chain by correlation id. Filter by event kind or search the JSON. Every
          row carries the FR-017a fields when applicable.
        </p>
      </header>

      <div className="panel">
        <div className="panel-header">Query</div>
        <div className="p-4 flex flex-wrap gap-2 items-end">
          <label className="text-xs text-zinc-400 flex flex-col gap-1 flex-1 min-w-[260px]">
            correlation_id
            <input
              type="text"
              value={cidInput}
              onChange={(e) => setCidInput(e.target.value)}
              className="font-mono text-sm bg-zinc-950 border border-zinc-800 rounded-md px-3 py-1.5 text-zinc-100 focus:outline-none focus:ring-1 focus:ring-accent-500"
              aria-label="correlation_id"
            />
          </label>
          <label className="text-xs text-zinc-400 flex flex-col gap-1">
            kind
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-1.5 text-sm text-zinc-100"
              aria-label="kind filter"
            >
              <option value="">all</option>
              {KIND_OPTIONS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-zinc-400 flex flex-col gap-1 flex-1 min-w-[200px]">
            free-text
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="search the chain JSON…"
              className="text-sm bg-zinc-950 border border-zinc-800 rounded-md px-3 py-1.5 text-zinc-100"
              aria-label="free text filter"
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              setCid(cidInput);
              const next = new URLSearchParams(params);
              next.set("cid", cidInput);
              setParams(next);
            }}
          >
            Fetch
          </button>
        </div>
      </div>

      {audit.error ? (
        <div className="pill-bad" role="alert">
          {audit.error instanceof ApiError
            ? `${audit.error.status} · ${audit.error.code} — ${audit.error.message}`
            : (audit.error as Error).message}
        </div>
      ) : null}

      <div>
        <div className="text-xs text-zinc-500 mb-2">
          {audit.isFetching ? "Fetching…" : `${visible.length} of ${audit.data?.length ?? 0} events`}
        </div>
        <AuditChain
          events={visible}
          emptyHint="No matching events."
          highlightKinds={["generated", "outcome"]}
        />
      </div>
    </div>
  );
}
