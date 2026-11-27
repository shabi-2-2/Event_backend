import { describe, expect, it } from "vitest";
import type { CheckinResponse } from "@/lib/api/contracts";
import {
  createInitialScannerState,
  scannerReducer,
  type ScannerErrorInfo,
} from "@/lib/scanner/state";

const TOKEN = "raw-ticket-token-1234567890";
const ERROR: ScannerErrorInfo = {
  title: "Network error",
  description: "Try again.",
  retryable: true,
};

const ticket = {
  attendee_name: "Ada Lovelace",
  urn: "student-1",
  ticket_status: "active" as const,
  registration_status: "registered" as const,
  check_in_status: "pending" as const,
};

function response(outcome: CheckinResponse["outcome"]): CheckinResponse {
  return {
    success: outcome === "valid_ticket" || outcome === "checked_in",
    outcome,
    message: `Outcome ${outcome}`,
    ticket: outcome === "invalid_ticket" ? null : ticket,
  };
}

describe("scanner state machine", () => {
  it("follows the explicit start, scan, verify, confirm path", () => {
    let state = createInitialScannerState("summit");
    state = scannerReducer(state, { type: "CAMERA_START", eventSlug: "summit" });
    expect(state.phase).toBe("requesting_camera");

    state = scannerReducer(state, { type: "CAMERA_READY", eventSlug: "summit" });
    expect(state.phase).toBe("scanning");

    state = scannerReducer(state, {
      type: "TOKEN_ACCEPTED",
      eventSlug: "summit",
      token: TOKEN,
    });
    expect(state).toMatchObject({ phase: "verifying", token: TOKEN });

    state = scannerReducer(state, {
      type: "VERIFY_SUCCEEDED",
      eventSlug: "summit",
      token: TOKEN,
      response: response("valid_ticket"),
    });
    expect(state).toMatchObject({
      phase: "confirmation_required",
      token: TOKEN,
    });

    state = scannerReducer(state, {
      type: "CONFIRM_START",
      eventSlug: "summit",
      token: TOKEN,
    });
    expect(state.phase).toBe("confirming");

    state = scannerReducer(state, {
      type: "CONFIRM_SUCCEEDED",
      eventSlug: "summit",
      token: TOKEN,
      response: response("checked_in"),
    });
    expect(state.phase).toBe("checked_in");
    expect(state).not.toHaveProperty("token");
  });

  it("ignores duplicate verification and confirmation transitions", () => {
    let state = scannerReducer(createInitialScannerState("summit"), {
      type: "TOKEN_ACCEPTED",
      eventSlug: "summit",
      token: TOKEN,
    });
    const duplicate = scannerReducer(state, {
      type: "TOKEN_ACCEPTED",
      eventSlug: "summit",
      token: TOKEN,
    });
    expect(duplicate).toBe(state);

    state = scannerReducer(state, {
      type: "VERIFY_SUCCEEDED",
      eventSlug: "summit",
      token: TOKEN,
      response: response("valid_ticket"),
    });
    state = scannerReducer(state, {
      type: "CONFIRM_START",
      eventSlug: "summit",
      token: TOKEN,
    });
    expect(scannerReducer(state, {
      type: "CONFIRM_START",
      eventSlug: "summit",
      token: TOKEN,
    })).toBe(state);

    state = scannerReducer(state, {
      type: "CONFIRM_SUCCEEDED",
      eventSlug: "summit",
      token: TOKEN,
      response: response("checked_in"),
    });
    expect(scannerReducer(state, {
      type: "CONFIRM_SUCCEEDED",
      eventSlug: "summit",
      token: TOKEN,
      response: response("checked_in"),
    })).toBe(state);
  });

  it("maps every non-valid verify outcome to its authoritative terminal state", () => {
    const cases: Array<[CheckinResponse["outcome"], ScannerStatePhase]> = [
      ["checked_in", "checked_in"],
      ["already_checked_in", "already_checked_in"],
      ["invalid_ticket", "denied"],
      ["revoked_ticket", "denied"],
      ["expired_ticket", "denied"],
      ["registration_cancelled", "denied"],
      ["invalid_registration_state", "denied"],
    ];

    for (const [outcome, phase] of cases) {
      const state = scannerReducer(
        scannerReducer(createInitialScannerState("summit"), {
          type: "TOKEN_ACCEPTED",
          eventSlug: "summit",
          token: TOKEN,
        }),
        {
          type: "VERIFY_SUCCEEDED",
          eventSlug: "summit",
          token: TOKEN,
          response: response(outcome),
        },
      );

      expect(state.phase).toBe(phase);
      if ("response" in state) {
        expect(state.response.outcome).toBe(outcome);
      }
    }
  });

  it("discards stale event and token results", () => {
    let state = scannerReducer(createInitialScannerState("summit"), {
      type: "TOKEN_ACCEPTED",
      eventSlug: "summit",
      token: TOKEN,
    });

    expect(scannerReducer(state, {
      type: "VERIFY_SUCCEEDED",
      eventSlug: "other-event",
      token: TOKEN,
      response: response("valid_ticket"),
    })).toBe(state);

    expect(scannerReducer(state, {
      type: "VERIFY_SUCCEEDED",
      eventSlug: "summit",
      token: "different-token-value-123456",
      response: response("valid_ticket"),
    })).toBe(state);

    state = scannerReducer(state, {
      type: "EVENT_CHANGED",
      eventSlug: "other-event",
    });
    expect(state).toEqual(createInitialScannerState("other-event"));
  });

  it("uses camera and request error states for failures and safe resets", () => {
    let state = scannerReducer(createInitialScannerState("summit"), {
      type: "CAMERA_START",
      eventSlug: "summit",
    });

    state = scannerReducer(state, {
      type: "CAMERA_DENIED",
      eventSlug: "summit",
      error: ERROR,
    });
    expect(state).toMatchObject({ phase: "camera_denied", error: ERROR });

    state = scannerReducer(state, { type: "RESET", eventSlug: "summit" });
    expect(state.phase).toBe("idle");

    state = scannerReducer(state, {
      type: "TOKEN_ACCEPTED",
      eventSlug: "summit",
      token: TOKEN,
    });
    state = scannerReducer(state, {
      type: "VERIFY_FAILED",
      eventSlug: "summit",
      token: TOKEN,
      error: ERROR,
    });
    expect(state).toMatchObject({ phase: "request_error", error: ERROR });
    expect(state).not.toHaveProperty("token");
  });
});

type ScannerStatePhase =
  | "checked_in"
  | "already_checked_in"
  | "denied";
