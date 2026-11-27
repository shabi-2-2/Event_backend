import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptyPage() {
  return { items: [], page: 1, page_size: 25, total: 0 };
}

describe("management ApiClient methods", () => {
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

  it("creates, updates, publishes, and archives events with exact paths", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse({ slug: "test-event" }));
    const client = new ApiClient(async () => "token");

    await client.events.create({ slug: "test-event", name: "Test", starts_at: "a", ends_at: "b", timezone: "UTC" });
    await client.events.update("test-event", { name: "Updated" });
    await client.events.publish("test-event");
    await client.events.archive("test-event");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example/api/v1/admin/events",
      "https://api.example/api/v1/admin/events/test-event",
      "https://api.example/api/v1/admin/events/test-event/publish",
      "https://api.example/api/v1/admin/events/test-event/archive",
    ]);
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("PATCH");
    expect(fetchMock.mock.calls[2][1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[3][1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[1][1]?.body).toBe(JSON.stringify({ name: "Updated" }));
  });

  it("lists and fetches attendees with exact filters and paths", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse(emptyPage()));
    const client = new ApiClient(async () => "token");

    await client.attendees.list("my-event", {
      page: 2,
      page_size: 10,
      search: "ada",
      urn: "URN-1",
      registration_status: "registered",
      ticket_status: "active",
      check_in_status: "pending",
      sort_by: "name",
      sort_order: "asc",
    });
    await client.attendees.get("my-event", "att-1");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/attendees?page=2&page_size=10&search=ada&urn=URN-1&registration_status=registered&ticket_status=active&check_in_status=pending&sort_by=name&sort_order=asc",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/attendees/att-1",
    );
  });

  it("omits undefined filters and never sends an empty email filter", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse(emptyPage()));
    const client = new ApiClient(async () => "token");

    await client.attendees.list("my-event", {
      page: 1,
      page_size: 25,
      email: undefined,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/attendees?page=1&page_size=25",
    );
  });

  it("lists, fetches, and cancels registrations with exact paths", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse(emptyPage()));
    const client = new ApiClient(async () => "token");

    await client.registrations.list("my-event", {
      reference: "reg",
      name: "Ada",
      email: "ada@example.com",
      registration_status: "registered",
      ticket_status: "active",
      check_in_status: "pending",
    });
    await client.registrations.get("my-event", "reg-1");
    await client.registrations.cancel("my-event", "reg-1");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/registrations?reference=reg&name=Ada&email=ada%40example.com&registration_status=registered&ticket_status=active&check_in_status=pending",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/registrations/reg-1",
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/registrations/reg-1/cancel",
    );
    expect(fetchMock.mock.calls[2][1]?.method).toBe("POST");
  });

  it("lists, revokes, and resends tickets with exact paths", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse(emptyPage()));
    const client = new ApiClient(async () => "token");

    await client.tickets.list("my-event", { ticket_status: "active", reference: "tkt" });
    await client.tickets.revoke("my-event", "tkt-1");
    await client.tickets.resend("my-event", "tkt-1");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/tickets?ticket_status=active&reference=tkt",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/tickets/tkt-1/revoke",
    );
    expect(fetchMock.mock.calls[2][0]).toBe(
      "https://api.example/api/v1/admin/events/my-event/tickets/tkt-1/resend",
    );
  });

  it("lists, creates, updates, and removes staff with exact paths and bodies", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse(emptyPage()));
    const client = new ApiClient(async () => "token");

    await client.staff.list("my-event", { role: "checkin" });
    await client.staff.create("my-event", { user_id: "user-1", role: "viewer" });
    await client.staff.updateRole("my-event", "user-1", { role: "admin" });
    await client.staff.remove("my-event", "user-1");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example/api/v1/admin/events/my-event/staff?role=checkin",
      "https://api.example/api/v1/admin/events/my-event/staff",
      "https://api.example/api/v1/admin/events/my-event/staff/user-1",
      "https://api.example/api/v1/admin/events/my-event/staff/user-1",
    ]);
    expect(fetchMock.mock.calls[1][1]?.body).toBe(
      JSON.stringify({ user_id: "user-1", role: "viewer" }),
    );
    expect(fetchMock.mock.calls[2][1]?.method).toBe("PATCH");
    expect(fetchMock.mock.calls[2][1]?.body).toBe(JSON.stringify({ role: "admin" }));
    expect(fetchMock.mock.calls[3][1]?.method).toBe("DELETE");
  });
});
