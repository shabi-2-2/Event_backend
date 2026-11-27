import type { CheckinOutcome } from "@/lib/api/contracts";
import type { ScannerState } from "@/lib/scanner/state";

export function outcomeTitle(outcome: CheckinOutcome): string {
  switch (outcome) {
    case "valid_ticket":
      return "Ticket verified";
    case "checked_in":
      return "Check-in confirmed";
    case "already_checked_in":
      return "Already checked in";
    case "invalid_ticket":
      return "Invalid ticket";
    case "revoked_ticket":
      return "Revoked ticket";
    case "expired_ticket":
      return "Expired ticket";
    case "registration_cancelled":
      return "Registration cancelled";
    case "invalid_registration_state":
      return "Registration not eligible";
  }
}

export function outcomeVariant(
  outcome: CheckinOutcome,
): "default" | "destructive" | "warning" {
  if (outcome === "checked_in" || outcome === "valid_ticket") {
    return "default";
  }
  if (
    outcome === "already_checked_in" ||
    outcome === "revoked_ticket" ||
    outcome === "expired_ticket"
  ) {
    return "warning";
  }
  return "destructive";
}

/** Screen-reader announcement for the current state; never includes a token. */
export function scannerAnnouncement(state: ScannerState): string {
  switch (state.phase) {
    case "idle":
      return "Scanner ready. Start the camera or enter a ticket token manually.";
    case "requesting_camera":
      return "Requesting camera permission.";
    case "scanning":
      return "Camera active. Point it at a ticket QR code.";
    case "verifying":
      return "Verifying ticket.";
    case "confirmation_required":
      return `${outcomeTitle(state.response.outcome)}. ${state.response.message} Confirmation is required before check-in.`;
    case "confirming":
      return "Confirming check-in.";
    case "checked_in":
    case "already_checked_in":
    case "denied":
      return `${outcomeTitle(state.response.outcome)}. ${state.response.message}`;
    case "camera_denied":
      return state.error.title;
    case "camera_unavailable":
      return state.error.title;
    case "request_error":
      return state.error.title;
  }
}
