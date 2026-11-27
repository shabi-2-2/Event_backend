import type { ValidationIssue } from "@/lib/api/contracts";

const FALLBACK_CODES: Record<number, string> = {
  400: "BAD_REQUEST",
  401: "UNAUTHORIZED",
  403: "FORBIDDEN",
  404: "NOT_FOUND",
  405: "METHOD_NOT_ALLOWED",
  409: "CONFLICT",
  422: "VALIDATION_ERROR",
  429: "TOO_MANY_REQUESTS",
  500: "INTERNAL_SERVER_ERROR",
};

const FALLBACK_MESSAGES: Record<number, string> = {
  400: "The request could not be understood.",
  401: "Authentication is required.",
  403: "You do not have access to this resource.",
  404: "The requested resource was not found.",
  405: "This method is not allowed for the resource.",
  409: "The request conflicts with the current state.",
  422: "Request validation failed.",
  429: "Too many requests. Please retry later.",
  500: "An unexpected error occurred.",
};

function fallbackCode(status: number): string {
  return FALLBACK_CODES[status] ?? (status >= 500 ? "INTERNAL_SERVER_ERROR" : "HTTP_ERROR");
}

function fallbackMessage(status: number): string {
  return FALLBACK_MESSAGES[status] ?? "The request could not be completed.";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: ValidationIssue[];

  constructor(
    status: number,
    code: string,
    message: string,
    details?: ValidationIssue[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    const contentType = response.headers.get("content-type") ?? "";
    let payload: unknown = null;

    if (contentType.includes("application/json")) {
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
    } else {
      try {
        const text = await response.text();
        payload = text ? { error: { message: text.slice(0, 300) } } : null;
      } catch {
        payload = null;
      }
    }

    const envelope =
      isRecord(payload) && isRecord(payload.error) ? payload.error : null;
    const code =
      envelope && typeof envelope.code === "string"
        ? envelope.code
        : fallbackCode(response.status);
    const message =
      envelope && typeof envelope.message === "string"
        ? envelope.message
        : fallbackMessage(response.status);
    const details =
      envelope && Array.isArray(envelope.details)
        ? (envelope.details.filter(isRecord) as ValidationIssue[])
        : undefined;

    return new ApiError(response.status, code, message, details);
  }

  get isUnauthorized(): boolean {
    return this.status === 401 || this.code === "UNAUTHORIZED";
  }

  get isForbidden(): boolean {
    return this.status === 403 || this.code === "FORBIDDEN";
  }

  get isValidationError(): boolean {
    return this.status === 422;
  }

  get isRateLimited(): boolean {
    return this.status === 429 || this.code === "TOO_MANY_REQUESTS";
  }

  get retryAfterSeconds(): number | null {
    const retryAfter = this.details?.find(
      (detail) => typeof detail.retry_after_seconds === "number",
    )?.retry_after_seconds;

    return typeof retryAfter === "number" ? retryAfter : null;
  }
}
