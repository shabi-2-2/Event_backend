import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string) {
  return jsonResponse({ error: { code, message } }, status);
}

function requestCall(call: unknown): { url: URL; init?: RequestInit } {
  const values = call as [RequestInfo | URL, RequestInit?];
  return { url: new URL(String(values[0])), init: values[1] };
}

describe("operational ApiClient methods", () => {
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

  function createClient() {
    return new ApiClient(async () => "access-token");
  }

  it("lists email deliveries with exact paths and supported filters", async () => {
    const page = { items: [], page: 2, page_size: 25, total: 0 };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(page));

    const result = await createClient().emailDeliveries.list("summit-2026", {
      page: 2,
      page_size: 25,
      status: "failed",
      registration_reference: "reg-1",
      ticket_reference: "tkt-1",
      min_attempts: 1,
      max_attempts: 5,
      error_code: "SMTP_TIMEOUT",
      next_attempt_after: "2026-06-01T00:00:00Z",
      next_attempt_before: "2026-06-02T00:00:00Z",
    });

    expect(result).toEqual(page);
    const { url, init } = requestCall(vi.mocked(fetch).mock.calls[0]);
    expect(url.pathname).toBe("/api/v1/admin/events/summit-2026/email-deliveries");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      page: "2",
      page_size: "25",
      status: "failed",
      registration_reference: "reg-1",
      ticket_reference: "tkt-1",
      min_attempts: "1",
      max_attempts: "5",
      error_code: "SMTP_TIMEOUT",
      next_attempt_after: "2026-06-01T00:00:00Z",
      next_attempt_before: "2026-06-02T00:00:00Z",
    });
    expect(init?.method).toBe("GET");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer access-token");
  });

  it("retries an email delivery through the existing POST operation", async () => {
    const retryResult = {
      delivery_reference: "del-1",
      registration_reference: "reg-1",
      ticket_reference: "tkt-1",
      status: "pending",
      resend_sequence: 1,
      previous_status: "failed",
      message: "Replacement job queued.",
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(retryResult));

    const result = await createClient().emailDeliveries.retry("summit-2026", "del-1");

    expect(result).toEqual(retryResult);
    const { url, init } = requestCall(vi.mocked(fetch).mock.calls[0]);
    expect(url.pathname).toBe(
      "/api/v1/admin/events/summit-2026/email-deliveries/del-1/retry",
    );
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
  });

  it("lists audit logs with exact paths and supported filters", async () => {
    const page = { items: [], page: 1, page_size: 25, total: 0 };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(page));

    const result = await createClient().auditLogs.list("summit-2026", {
      page: 1,
      page_size: 25,
      action: "ticket.revoked",
      actor_user_id: "11111111-1111-4111-8111-111111111111",
      from_date: "2026-06-01T00:00:00Z",
      to_date: "2026-06-02T00:00:00Z",
      sort_order: "asc",
    });

    expect(result).toEqual(page);
    const { url, init } = requestCall(vi.mocked(fetch).mock.calls[0]);
    expect(url.pathname).toBe("/api/v1/admin/events/summit-2026/audit-logs");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      page: "1",
      page_size: "25",
      action: "ticket.revoked",
      actor_user_id: "11111111-1111-4111-8111-111111111111",
      from_date: "2026-06-01T00:00:00Z",
      to_date: "2026-06-02T00:00:00Z",
      sort_order: "asc",
    });
    expect(init?.method).toBe("GET");
  });

  it("downloads backend exports with authoritative filename and content type", async () => {
    const body = "attendee_reference,name\natt-1,Ada Lovelace\n";
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(body, {
        status: 200,
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
          "Content-Disposition": 'attachment; filename="attendees-summit-2026.csv"',
        },
      }),
    );

    const file = await createClient().exports.download("summit-2026", "attendees", "csv");

    expect(file.filename).toBe("attendees-summit-2026.csv");
    expect(file.contentType).toBe("text/csv; charset=utf-8");
    expect(await file.blob.text()).toBe(body);

    const { url, init } = requestCall(vi.mocked(fetch).mock.calls[0]);
    expect(url.pathname).toBe("/api/v1/admin/events/summit-2026/exports/attendees.csv");
    expect(url.search).toBe("");
    expect(init?.method).toBe("GET");
  });

  it("propagates unauthorized email errors from the backend", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      errorResponse(401, "UNAUTHORIZED", "Sign in again."),
    );

    await expect(createClient().emailDeliveries.list("summit-2026")).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
      message: "Sign in again.",
    });
  });

  it("propagates forbidden audit errors from the backend", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      errorResponse(403, "FORBIDDEN", "Admin access required."),
    );

    const request = createClient().auditLogs.list("summit-2026");
    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      status: 403,
      code: "FORBIDDEN",
    });
  });

  it("propagates rate-limit details for export requests", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: "TOO_MANY_REQUESTS",
            message: "Too many requests.",
            details: [{ retry_after_seconds: 12 }],
          },
        },
        429,
      ),
    );

    await expect(
      createClient().exports.download("summit-2026", "checkins", "xlsx"),
    ).rejects.toMatchObject({ status: 429, code: "TOO_MANY_REQUESTS", retryAfterSeconds: 12 });
  });
});
