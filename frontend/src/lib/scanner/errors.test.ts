import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { insecureContextError, toCameraError, toScannerError } from "@/lib/scanner/errors";

describe("scanner error mapping", () => {
  it("maps documented HTTP failures without exposing response bodies", () => {
    expect(toScannerError(new ApiError(401, "UNAUTHORIZED", "nope"))).toMatchObject({
      status: 401,
      title: "Authentication required",
      retryable: false,
    });
    expect(toScannerError(new ApiError(403, "FORBIDDEN", "nope"))).toMatchObject({
      status: 403,
      title: "Scanner access denied",
      retryable: false,
    });
    expect(toScannerError(new ApiError(404, "NOT_FOUND", "nope"))).toMatchObject({
      status: 404,
      title: "Event unavailable",
    });
    expect(toScannerError(new ApiError(409, "CONFLICT", "nope"))).toMatchObject({
      status: 409,
      title: "Check-in conflict",
    });
    expect(toScannerError(new ApiError(422, "VALIDATION_ERROR", "nope"))).toMatchObject({
      status: 422,
      title: "Token not accepted",
    });
    expect(
      toScannerError(
        new ApiError(429, "TOO_MANY_REQUESTS", "nope", [{ retry_after_seconds: 12 }]),
      ),
    ).toMatchObject({
      status: 429,
      title: "Too many requests",
      description: "Please wait 12 seconds before scanning again.",
      retryable: true,
    });
  });

  it("maps network and unexpected server failures", () => {
    expect(toScannerError(new Error("offline"))).toMatchObject({
      title: "Network error",
      description: "offline",
      retryable: true,
    });
    expect(toScannerError(new ApiError(500, "INTERNAL_SERVER_ERROR", "down"))).toMatchObject({
      status: 500,
      title: "Scanner service error",
      retryable: true,
    });
  });

  it("separates camera denial, unavailable devices, and insecure contexts", () => {
    expect(toCameraError(new DOMException("blocked", "NotAllowedError")).title).toBe(
      "Camera permission denied",
    );
    expect(toCameraError(new DOMException("missing", "NotFoundError")).title).toBe(
      "Camera unavailable",
    );
    expect(insecureContextError().title).toBe("Secure connection required");
  });
});
