import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("analytics API integration", () => {
  const originalBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example/api/v1";
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

  it("calls the exact overview endpoint", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ total_registrations: 1 }));

    const client = new ApiClient(async () => "token");
    await client.analytics.overview("summer-summit");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/summer-summit/analytics/overview",
    );
  });

  it("sends timezone-aware query parameters for registration and attendance trends", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse({ buckets: [] }));

    const client = new ApiClient(async () => "token");
    const range = {
      from_date: "2026-01-01T00:00:00.000Z",
      to_date: "2026-01-31T23:59:59.999Z",
    };

    await client.analytics.registrations("summer-summit", range);
    await client.analytics.attendance("summer-summit", range);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/summer-summit/analytics/registrations?from_date=2026-01-01T00%3A00%3A00.000Z&to_date=2026-01-31T23%3A59%3A59.999Z",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "https://api.example/api/v1/admin/events/summer-summit/analytics/attendance?from_date=2026-01-01T00%3A00%3A00.000Z&to_date=2026-01-31T23%3A59%3A59.999Z",
    );
  });

  it("omits date parameters when no range is selected", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ buckets: [] }));

    const client = new ApiClient(async () => "token");
    await client.analytics.registrations("summer-summit");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/summer-summit/analytics/registrations",
    );
  });

  it("calls the exact email analytics endpoint", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ total_deliveries: 0 }));

    const client = new ApiClient(async () => "token");
    await client.analytics.emailDeliveries("summer-summit");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/summer-summit/analytics/email-deliveries",
    );
  });

  it("encodes event slugs safely", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ total_registrations: 0 }));

    const client = new ApiClient(async () => "token");
    await client.analytics.overview("event/with spaces");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/event%2Fwith%20spaces/analytics/overview",
    );
  });
});
