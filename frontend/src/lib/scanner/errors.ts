import { ApiError } from "@/lib/api/errors";
import type { ScannerErrorInfo } from "@/lib/scanner/state";

export function toScannerError(error: unknown): ScannerErrorInfo {
  if (error instanceof ApiError) {
    const base = { status: error.status };

    switch (error.status) {
      case 401:
        return {
          ...base,
          title: "Authentication required",
          description: "Your session is no longer valid. Sign in again to continue.",
          retryable: false,
        };
      case 403:
        return {
          ...base,
          title: "Scanner access denied",
          description: "Your event staff role does not allow this scanner action.",
          retryable: false,
        };
      case 404:
        return {
          ...base,
          title: "Event unavailable",
          description: error.message || "The requested event was not found.",
          retryable: false,
        };
      case 409:
        return {
          ...base,
          title: "Check-in conflict",
          description: error.message || "The ticket state changed. Scan it again to see the current result.",
          retryable: false,
        };
      case 422:
        return {
          ...base,
          title: "Token not accepted",
          description: error.message || "Check that the raw ticket token is complete and try again.",
          retryable: false,
        };
      case 429:
        return {
          ...base,
          title: "Too many requests",
          description: error.retryAfterSeconds
            ? `Please wait ${error.retryAfterSeconds} seconds before scanning again.`
            : "Please wait before scanning again.",
          retryable: true,
        };
      default:
        return {
          ...base,
          title: error.status >= 500 ? "Scanner service error" : "Request failed",
          description: error.message || "The scanner request could not be completed.",
          retryable: true,
        };
    }
  }

  if (error instanceof DOMException) {
    return {
      title: "Scanner request failed",
      description: error.message || "The scanner could not complete the request.",
      retryable: true,
    };
  }

  return {
    title: "Network error",
    description:
      error instanceof Error && error.message
        ? error.message
        : "Check your connection and try again.",
    retryable: true,
  };
}

export function toCameraError(error: unknown): ScannerErrorInfo {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return {
        title: "Camera permission denied",
        description:
          "Allow camera access for this site in your browser settings, then start scanning again.",
        retryable: false,
      };
    }

    return {
      title: "Camera unavailable",
      description:
        error.message ||
        "No usable camera was found. You can still enter a raw ticket token manually.",
      retryable: true,
    };
  }

  return {
    title: "Camera unavailable",
    description:
      error instanceof Error && error.message
        ? error.message
        : "The camera could not be started. You can enter a raw ticket token manually.",
    retryable: true,
  };
}

export function insecureContextError(): ScannerErrorInfo {
  return {
    title: "Secure connection required",
    description:
      "Camera access requires HTTPS or localhost. Use a secure deployment URL, or enter a raw ticket token manually.",
    retryable: false,
  };
}

export function unexpectedResponseError(): ScannerErrorInfo {
  return {
    title: "Unexpected scanner response",
    description:
      "The server returned a response this scanner could not interpret. Scan the ticket again.",
    retryable: true,
  };
}
