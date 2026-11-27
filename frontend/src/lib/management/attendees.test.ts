import { describe, expect, it } from "vitest";
import type {
  AdminAttendeeRecord,
  ViewerAttendeeRecord,
} from "@/lib/api/contracts";
import {
  hasAdminAttendeeData,
  isAdminAttendee,
  RESTRICTED_ATTENDEE_FIELDS,
} from "@/lib/management/attendees";

const base: ViewerAttendeeRecord = {
  attendee_reference: "att-1",
  full_name: "Ada Lovelace",
  urn: "URN-001",
  registration_status: "registered",
  ticket_status: "active",
  check_in_status: "pending",
  checked_in_at: null,
};

const admin: AdminAttendeeRecord = {
  ...base,
  email: "ada@example.com",
  phone: null,
  registration_reference: "reg-1",
  registered_at: "2026-06-01T00:00:00Z",
  cancelled_at: null,
  ticket_reference: "tkt-1",
  ticket_expires_at: null,
  ticket_used_at: null,
  check_in_at: null,
  station: null,
};

describe("attendee privacy helpers", () => {
  it("detects admin records from the backend response shape", () => {
    expect(isAdminAttendee(admin)).toBe(true);
    expect(isAdminAttendee(base)).toBe(false);
  });

  it("detects admin data across a page of records", () => {
    expect(hasAdminAttendeeData([base, admin])).toBe(true);
    expect(hasAdminAttendeeData([base])).toBe(false);
    expect(hasAdminAttendeeData([])).toBe(false);
  });

  it("lists restricted fields without ticket secrets", () => {
    expect(RESTRICTED_ATTENDEE_FIELDS).toContain("email");
    expect(RESTRICTED_ATTENDEE_FIELDS).not.toContain("token");
    expect(RESTRICTED_ATTENDEE_FIELDS).not.toContain("qr");
  });
});
