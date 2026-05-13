import { useModeStore } from "@/store/mode";
import { useTokensStore, type PrincipalKey } from "@/store/tokens";
import { resolveFixture } from "./fixtures";

export interface RequestOptions {
  method: "GET" | "POST";
  path: string;
  principal?: PrincipalKey;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfterSeconds?: number;
  readonly correlationId?: string;
  readonly details?: unknown;

  constructor(args: {
    status: number;
    code: string;
    message: string;
    retryAfterSeconds?: number;
    correlationId?: string;
    details?: unknown;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.retryAfterSeconds = args.retryAfterSeconds;
    this.correlationId = args.correlationId;
    this.details = args.details;
  }
}

function buildQuery(query?: Record<string, string | number | undefined>): string {
  if (!query) return "";
  const entries = Object.entries(query).filter(
    ([, v]) => v !== undefined && v !== null,
  );
  if (entries.length === 0) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of entries) sp.set(k, String(v));
  return `?${sp.toString()}`;
}

export async function apiCall<T = unknown>(opts: RequestOptions): Promise<T> {
  const { mode, baseUrl } = useModeStore.getState();
  const { tokens } = useTokensStore.getState();
  const principalToken = opts.principal ? tokens[opts.principal] : undefined;

  if (mode === "recorded") {
    const hit = resolveFixture({
      method: opts.method,
      path: opts.path,
      principal: opts.principal,
      body: opts.body,
    });
    if (!hit) {
      throw new ApiError({
        status: 404,
        code: "FIXTURE_MISS",
        message: `No recorded fixture for ${opts.method} ${opts.path}`,
      });
    }
    if (hit.status >= 400) {
      throw new ApiError({
        status: hit.status,
        code: extractCode(hit.body) ?? `HTTP_${hit.status}`,
        message: extractMessage(hit.body) ?? `Request failed (${hit.status})`,
        retryAfterSeconds: hit.retryAfterSeconds,
        details: hit.body,
      });
    }
    return hit.body as T;
  }

  const url = `${baseUrl}${opts.path}${buildQuery(opts.query)}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (principalToken) headers["Authorization"] = `Bearer ${principalToken}`;

  const response = await fetch(url, {
    method: opts.method,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  let parsed: unknown = undefined;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    parsed = await response.json().catch(() => undefined);
  }

  if (!response.ok) {
    const retryAfter = response.headers.get("retry-after");
    throw new ApiError({
      status: response.status,
      code: extractCode(parsed) ?? `HTTP_${response.status}`,
      message: extractMessage(parsed) ?? response.statusText,
      retryAfterSeconds: retryAfter ? Number.parseInt(retryAfter, 10) : undefined,
      correlationId: extractCorrelationId(parsed),
      details: parsed,
    });
  }
  return (parsed ?? {}) as T;
}

function extractCode(body: unknown): string | undefined {
  if (body && typeof body === "object" && "code" in body) {
    const code = (body as { code: unknown }).code;
    if (typeof code === "string") return code;
  }
  return undefined;
}

function extractMessage(body: unknown): string | undefined {
  if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;
    const reason = obj.reason ?? obj.message;
    if (typeof reason === "string") return reason;
  }
  return undefined;
}

function extractCorrelationId(body: unknown): string | undefined {
  if (body && typeof body === "object" && "correlation_id" in body) {
    const cid = (body as { correlation_id: unknown }).correlation_id;
    if (typeof cid === "string") return cid;
  }
  return undefined;
}
