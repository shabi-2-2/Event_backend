import type { CheckinResponse } from "@/lib/api/contracts";

export type ScannerErrorInfo = {
  title: string;
  description: string;
  retryable: boolean;
  status?: number;
};

type StateBase = { eventSlug: string };

type PassiveState = StateBase & {
  phase: "idle" | "requesting_camera" | "scanning";
};

type VerifyingState = StateBase & {
  phase: "verifying";
  token: string;
};

type ConfirmationRequiredState = StateBase & {
  phase: "confirmation_required";
  token: string;
  response: CheckinResponse;
};

type ConfirmingState = StateBase & {
  phase: "confirming";
  token: string;
  response: CheckinResponse;
};

type CheckedInState = StateBase & {
  phase: "checked_in";
  response: CheckinResponse;
};

type AlreadyCheckedInState = StateBase & {
  phase: "already_checked_in";
  response: CheckinResponse;
};

type DeniedState = StateBase & {
  phase: "denied";
  response: CheckinResponse;
};

type CameraErrorState = StateBase & {
  phase: "camera_denied" | "camera_unavailable";
  error: ScannerErrorInfo;
};

type RequestErrorState = StateBase & {
  phase: "request_error";
  error: ScannerErrorInfo;
};

export type ScannerState =
  | PassiveState
  | VerifyingState
  | ConfirmationRequiredState
  | ConfirmingState
  | CheckedInState
  | AlreadyCheckedInState
  | DeniedState
  | CameraErrorState
  | RequestErrorState;

export type ScannerAction =
  | { type: "EVENT_CHANGED"; eventSlug: string }
  | { type: "RESET"; eventSlug: string }
  | { type: "CAMERA_START"; eventSlug: string }
  | { type: "CAMERA_READY"; eventSlug: string }
  | { type: "CAMERA_DENIED"; eventSlug: string; error: ScannerErrorInfo }
  | { type: "CAMERA_UNAVAILABLE"; eventSlug: string; error: ScannerErrorInfo }
  | { type: "CAMERA_STOPPED"; eventSlug: string }
  | { type: "TOKEN_ACCEPTED"; eventSlug: string; token: string }
  | {
      type: "VERIFY_SUCCEEDED";
      eventSlug: string;
      token: string;
      response: CheckinResponse;
    }
  | { type: "VERIFY_FAILED"; eventSlug: string; token: string; error: ScannerErrorInfo }
  | { type: "CONFIRM_START"; eventSlug: string; token: string }
  | {
      type: "CONFIRM_SUCCEEDED";
      eventSlug: string;
      token: string;
      response: CheckinResponse;
    }
  | { type: "CONFIRM_FAILED"; eventSlug: string; token: string; error: ScannerErrorInfo };

export function createInitialScannerState(eventSlug: string): ScannerState {
  return { eventSlug, phase: "idle" };
}

function isCurrent(state: ScannerState, eventSlug: string): boolean {
  return state.eventSlug === eventSlug;
}

function terminalState(
  eventSlug: string,
  response: CheckinResponse,
): CheckedInState | AlreadyCheckedInState | DeniedState {
  if (response.outcome === "checked_in") {
    return { eventSlug, phase: "checked_in", response };
  }
  if (response.outcome === "already_checked_in") {
    return { eventSlug, phase: "already_checked_in", response };
  }
  return { eventSlug, phase: "denied", response };
}

/** Reduces only legal transitions; stale event/token actions are ignored. */
export function scannerReducer(state: ScannerState, action: ScannerAction): ScannerState {
  switch (action.type) {
    case "EVENT_CHANGED":
    case "RESET":
      return createInitialScannerState(action.eventSlug);

    case "CAMERA_START":
      if (!isCurrent(state, action.eventSlug) || state.phase !== "idle") {
        return state;
      }
      return { eventSlug: state.eventSlug, phase: "requesting_camera" };

    case "CAMERA_READY":
      if (!isCurrent(state, action.eventSlug) || state.phase !== "requesting_camera") {
        return state;
      }
      return { eventSlug: state.eventSlug, phase: "scanning" };

    case "CAMERA_DENIED":
      if (!isCurrent(state, action.eventSlug) || state.phase !== "requesting_camera") {
        return state;
      }
      return { eventSlug: state.eventSlug, phase: "camera_denied", error: action.error };

    case "CAMERA_UNAVAILABLE":
      if (!isCurrent(state, action.eventSlug) || state.phase !== "requesting_camera") {
        return state;
      }
      return {
        eventSlug: state.eventSlug,
        phase: "camera_unavailable",
        error: action.error,
      };

    case "CAMERA_STOPPED":
      if (
        !isCurrent(state, action.eventSlug) ||
        (state.phase !== "scanning" && state.phase !== "requesting_camera")
      ) {
        return state;
      }
      return { eventSlug: state.eventSlug, phase: "idle" };

    case "TOKEN_ACCEPTED":
      if (
        !isCurrent(state, action.eventSlug) ||
        (state.phase !== "idle" && state.phase !== "scanning") ||
        !action.token
      ) {
        return state;
      }
      return { eventSlug: state.eventSlug, phase: "verifying", token: action.token };

    case "VERIFY_SUCCEEDED":
      if (
        !isCurrent(state, action.eventSlug) ||
        state.phase !== "verifying" ||
        state.token !== action.token
      ) {
        return state;
      }
      if (action.response.outcome === "valid_ticket") {
        return {
          eventSlug: state.eventSlug,
          phase: "confirmation_required",
          token: state.token,
          response: action.response,
        };
      }
      return terminalState(state.eventSlug, action.response);

    case "VERIFY_FAILED":
      if (
        !isCurrent(state, action.eventSlug) ||
        state.phase !== "verifying" ||
        state.token !== action.token
      ) {
        return state;
      }
      return {
        eventSlug: state.eventSlug,
        phase: "request_error",
        error: action.error,
      };

    case "CONFIRM_START":
      if (
        !isCurrent(state, action.eventSlug) ||
        state.phase !== "confirmation_required" ||
        state.token !== action.token
      ) {
        return state;
      }
      return {
        eventSlug: state.eventSlug,
        phase: "confirming",
        token: state.token,
        response: state.response,
      };

    case "CONFIRM_SUCCEEDED":
      if (
        !isCurrent(state, action.eventSlug) ||
        state.phase !== "confirming" ||
        state.token !== action.token
      ) {
        return state;
      }
      return terminalState(state.eventSlug, action.response);

    case "CONFIRM_FAILED":
      if (
        !isCurrent(state, action.eventSlug) ||
        state.phase !== "confirming" ||
        state.token !== action.token
      ) {
        return state;
      }
      return {
        eventSlug: state.eventSlug,
        phase: "request_error",
        error: action.error,
      };

    default:
      return state;
  }
}
