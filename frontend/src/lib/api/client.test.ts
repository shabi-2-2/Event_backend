import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ApiClient", () => {
  const originalBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example/api/v1/";
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    if (originalBaseUrl === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_API_BASE_URL = originalBaseUrl;
    }
    vi.unstubAllGlobals();
  });

  it("attaches the Supabase access token and serializes query parameters", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ items: [], page: 2, page_size: 10, total: 0 }),
    );

    const client = new ApiClient(async () => "access-token-123");
    await client.events.list({ page: 2, page_size: 10, status: "published" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "https://api.example/api/v1/admin/events?page=2&page_size=10&status=published",
    );
    expect(init.method).toBe("GET");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer access-token-123");
    expect(init.cache).toBe("no-store");
  });

  it("does not send an Authorization header without an access token", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    const client = new ApiClient(async () => null);
    await client.request({ path: "/health" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Headers).has("Authorization")).toBe(false);
  });

  it("parses the backend error envelope", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "FORBIDDEN",
            message: "You do not have access to this resource.",
          },
        },
        403,
      ),
    );

    const client = new ApiClient(async () => "token");

    await expect(client.events.list()).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      code: "FORBIDDEN",
      message: "You do not have access to this resource.",
      isForbidden: true,
    });
  });

  it("preserves validation details and rate-limit retry metadata", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "Request validation failed.",
            details: [{ loc: ["query", "page"], msg: "Input should be >= 1", type: "greater_than_equal" }],
          },
        },
        422,
      ),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "TOO_MANY_REQUESTS",
            message: "Too many requests. Please retry later.",
            details: [{ retry_after_seconds: 30 }],
          },
        },
        429,
      ),
    );

    const client = new ApiClient(async () => "token");

    await expect(client.events.list({ page: 0 })).rejects.toMatchObject({
      status: 422,
      details: [{ loc: ["query", "page"], type: "greater_than_equal" }],
    });

    await expect(client.download("/admin/events/analytics/export")).rejects.toMatchObject({
      status: 429,
      isRateLimited: true,
      retryAfterSeconds: 30,
    });
  });

  it("returns binary responses as blobs", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response("id,name\n1,Example", {
        status: 200,
        headers: { "Content-Type": "text/csv" },
      }),
    );

    const client = new ApiClient(async () => "token");
    const blob = await client.download("/admin/events/demo/exports/attendees.csv");

    expect(blob).toBeInstanceOf(Blob);
    expect(await blob.text()).toContain("id,name");
  });
});
