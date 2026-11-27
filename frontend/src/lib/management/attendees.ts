import type {
  AdminAttendeeRecord,
  AttendeeRecord,
} from "@/lib/api/contracts";

/** Uses the backend response shape, never JWT claims, to identify admin-level attendee data. */
export function isAdminAttendee(
  record: AttendeeRecord,
): record is AdminAttendeeRecord {
  return "email" in record;
}

export function hasAdminAttendeeData(records: AttendeeRecord[]): boolean {
  return records.some(isAdminAttendee);
}

export const RESTRICTED_ATTENDEE_FIELDS = [
  "email",
  "phone",
  "registration reference",
  "registered at",
  "cancelled at",
  "ticket reference",
  "ticket expiry",
  "ticket usage time",
  "check-in time",
  "check-in station",
] as const;
