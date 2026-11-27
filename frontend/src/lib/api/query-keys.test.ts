import { describe, expect, it } from "vitest";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";

describe("management query keys", () => {
  it("scopes every resource key to the event slug", () => {
    expect(managementKeys.event("event-a")).toEqual(["management", "event-a", "event"]);
    expect(managementKeys.attendee("event-a", "att-1")).toEqual([
      "management",
      "event-a",
      "attendee",
      "att-1",
    ]);
    expect(managementKeys.registration("event-a", "reg-1")).toEqual([
      "management",
      "event-a",
      "registration",
      "reg-1",
    ]);
  });

  it("does not collide across events", () => {
    expect(managementKeys.tickets("event-a")).not.toEqual(
      managementKeys.tickets("event-b"),
    );
    expect(managementKeys.attendees("event-a")).not.toEqual(
      managementKeys.attendees("event-b"),
    );
    expect(managementKeys.emailDeliveries("event-a")).not.toEqual(
      managementKeys.emailDeliveries("event-b"),
    );
    expect(managementKeys.auditLogs("event-a")).not.toEqual(
      managementKeys.auditLogs("event-b"),
    );
  });

  it("includes filters so switching filters never reuses stale pages", () => {
    const active = managementKeys.tickets("event-a", { ticket_status: "active" });
    const used = managementKeys.tickets("event-a", { ticket_status: "used" });
    expect(active).not.toEqual(used);

    const viewer = managementKeys.attendees("event-a", { search: "ada" });
    const all = managementKeys.attendees("event-a", {});
    expect(viewer).not.toEqual(all);
  });

  it("exposes prefixes that match every filtered list for invalidation", () => {
    expect(managementKeys.tickets("event-a", { ticket_status: "active" })).toEqual([
      ...managementKeys.ticketsAll("event-a"),
      '{"ticket_status":"active"}',
    ]);
    expect(managementKeys.attendees("event-a", { search: "ada" })).toEqual([
      ...managementKeys.attendeesAll("event-a"),
      '{"search":"ada"}',
    ]);
    expect(managementKeys.registrations("event-a", { page: 2 })).toEqual([
      ...managementKeys.registrationsAll("event-a"),
      '{"page":2}',
    ]);
    expect(managementKeys.staff("event-a", { role: "admin" })).toEqual([
      ...managementKeys.staffAll("event-a"),
      '{"role":"admin"}',
    ]);
    expect(managementKeys.emailDeliveries("event-a", { status: "failed" })).toEqual([
      ...managementKeys.emailDeliveriesAll("event-a"),
      '{"status":"failed"}',
    ]);
    expect(managementKeys.auditLogs("event-a", { sort_order: "asc" })).toEqual([
      ...managementKeys.auditLogsAll("event-a"),
      '{"sort_order":"asc"}',
    ]);
    expect(managementKeys.events({ page: 3 })).toEqual([
      ...managementKeys.eventsAll(),
      '{"page":3}',
    ]);
  });

  it("keeps dashboard invalidation broad enough for event switching", () => {
    expect(dashboardKeys.forEvent("event-a")[0]).toBe("dashboard");
    expect(managementKeys.all).toEqual(["management"]);
  });
});
