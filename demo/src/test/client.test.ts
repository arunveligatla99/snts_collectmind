import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { apiCall, ApiError } from "@/api/client";
import { useModeStore } from "@/store/mode";
import { useTokensStore } from "@/store/tokens";
import { resetStores } from "./utils";

describe("apiCall — recorded mode", () => {
  beforeEach(() => {
    resetStores();
    useModeStore.setState({ mode: "recorded" });
  });

  it("returns the body for a known fixture", async () => {
    const data = await apiCall({
      method: "GET",
      path: "/audit/01HW1A2B3C4D5E6F7G8H9J0KQA",
      principal: "tenant-a",
    });
    expect(Array.isArray(data)).toBe(true);
  });

  it("throws FIXTURE_MISS for unknown paths", async () => {
    await expect(
      apiCall({ method: "GET", path: "/nope", principal: "tenant-a" }),
    ).rejects.toMatchObject({ code: "FIXTURE_MISS", status: 404 });
  });

  it("throws ApiError with status + code on a recorded 404", async () => {
    await expect(
      apiCall({
        method: "GET",
        path: "/policies/pol-tenant-a-brake-wear",
        principal: "tenant-b",
      }),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("constructs an ApiError exposing details + retry-after", () => {
    const err = new ApiError({
      status: 429,
      code: "rate_limit_exceeded",
      message: "rate limited",
      retryAfterSeconds: 4,
      correlationId: "cid-x",
      details: { code: "rate_limit_exceeded" },
    });
    expect(err.status).toBe(429);
    expect(err.retryAfterSeconds).toBe(4);
    expect(err.correlationId).toBe("cid-x");
    expect(err.code).toBe("rate_limit_exceeded");
    expect(err.message).toBe("rate limited");
    expect(err.details).toEqual({ code: "rate_limit_exceeded" });
  });
});

describe("apiCall — live mode", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    resetStores();
    useModeStore.setState({ mode: "live", baseUrl: "/api/v1" });
    useTokensStore.setState((s) => ({ ...s, tokens: { ...s.tokens, "tenant-a": "tok-a" } }));
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("emits an Authorization header when a principal token is present", async () => {
    const seen: RequestInit[] = [];
    globalThis.fetch = vi.fn(async (_, init) => {
      seen.push(init as RequestInit);
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;
    const res = await apiCall<{ ok: boolean }>({
      method: "POST",
      path: "/findings",
      principal: "tenant-a",
      body: { hello: "world" },
    });
    expect(res.ok).toBe(true);
    const headers = seen[0]!.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok-a");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("surfaces 429 with Retry-After parsed into the ApiError", async () => {
    globalThis.fetch = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          code: "rate_limit_exceeded",
          message: "throttled",
          retry_after_seconds: 5,
        }),
        {
          status: 429,
          headers: { "content-type": "application/json", "retry-after": "5" },
        },
      );
    }) as unknown as typeof fetch;
    await expect(
      apiCall({ method: "POST", path: "/findings", principal: "tenant-a", body: {} }),
    ).rejects.toMatchObject({ status: 429, retryAfterSeconds: 5 });
  });

  it("appends query params and parses error responses", async () => {
    let seenUrl = "";
    globalThis.fetch = vi.fn(async (url) => {
      seenUrl = url as string;
      return new Response(
        JSON.stringify({ code: "NOT_FOUND", status: 404, reason: "missing" }),
        { status: 404, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    await expect(
      apiCall({
        method: "GET",
        path: "/policies/pol-x/versions",
        principal: "tenant-a",
        query: { limit: 5, skipped: undefined },
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND", status: 404 });
    expect(seenUrl).toContain("limit=5");
    expect(seenUrl).not.toContain("skipped=");
  });
});
