import type {
  CheckinOutcome,
  CheckinResponse,
  ScannerTicketInfo,
} from "@/lib/api/contracts";

const OUTCOMES: readonly CheckinOutcome[] = [
  "valid_ticket",
  "checked_in",
  "already_checked_in",
  "invalid_ticket",
  "revoked_ticket",
  "expired_ticket",
  "registration_cancelled",
  "invalid_registration_state",
];

const TICKET_STATUSES = ["active", "used", "revoked", "expired"];
const REGISTRATION_STATUSES = ["registered", "checked_in", "cancelled"];
const CHECKIN_STATUSES = ["pending", "checked_in"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isScannerTicketInfo(value: unknown): value is ScannerTicketInfo {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.attendee_name === "string" &&
    typeof value.urn === "string" &&
    TICKET_STATUSES.includes(String(value.ticket_status)) &&
    REGISTRATION_STATUSES.includes(String(value.registration_status)) &&
    CHECKIN_STATUSES.includes(String(value.check_in_status))
  );
}

/** Reject unexpected payloads without logging their contents. */
export function parseCheckinResponse(value: unknown): CheckinResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const { success, outcome, message, ticket } = value;
  if (
    typeof success !== "boolean" ||
    typeof outcome !== "string" ||
    !OUTCOMES.includes(outcome as CheckinOutcome) ||
    typeof message !== "string" ||
    (ticket !== null && !isScannerTicketInfo(ticket))
  ) {
    return null;
  }

  return {
    success,
    outcome: outcome as CheckinOutcome,
    message,
    ticket: ticket as ScannerTicketInfo | null,
  };
}
