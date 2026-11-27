import { ApiError } from "@/lib/api/errors";

export type ManagementErrorInfo = {
  title: string;
  description: string;
  retryable: boolean;
};

export function describeManagementError(error: unknown): ManagementErrorInfo {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return {
          title: "Authentication required",
          description: "Your session is no longer valid. Sign in again to continue.",
          retryable: false,
        };
      case 403:
        return {
          title: "Access restricted",
          description:
            error.message === "Email search is restricted to event administrators."
              ? error.message
              : "You do not have permission to manage this event.",
          retryable: false,
        };
      case 404:
        return {
          title: "Not found",
          description: error.message || "The requested resource was not found.",
          retryable: false,
        };
      case 409:
        return {
          title: "Conflict",
          description: error.message || "The request conflicts with the current state.",
          retryable: false,
        };
      case 422:
        return {
          title: "Invalid request",
          description: error.message || "Check the submitted values and try again.",
          retryable: false,
        };
      case 429:
        return {
          title: "Too many requests",
          description: error.retryAfterSeconds
            ? `Please retry in ${error.retryAfterSeconds} seconds.`
            : "Please wait before trying again.",
          retryable: true,
        };
      default:
        return {
          title: "Request failed",
          description: error.message || "The request could not be completed.",
          retryable: true,
        };
    }
  }

  return {
    title: "Network error",
    description:
      error instanceof Error && error.message
        ? error.message
        : "The request could not be completed. Check your connection and try again.",
    retryable: true,
  };
}

export function validationFieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.details) {
    return {};
  }

  const result: Record<string, string> = {};
  for (const detail of error.details) {
    if (typeof detail.msg !== "string") {
      continue;
    }

    const loc = Array.isArray(detail.loc)
      ? detail.loc.filter(
          (part): part is string | number =>
            typeof part === "string" || typeof part === "number",
        )
      : [];
    const field = String(loc.at(-1) ?? "form");
    result[field] = detail.msg;
  }

  return result;
}
