import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  describeManagementError,
  validationFieldErrors,
} from "@/lib/management/errors";

describe("describeManagementError", () => {
  it("maps authentication errors", () => {
    const info = describeManagementError(
      new ApiError(401, "UNAUTHORIZED", "Invalid or expired credentials."),
    );
    expect(info.title).toBe("Authentication required");
    expect(info.retryable).toBe(false);
  });

  it("maps forbidden errors including email search restriction", () => {
    const info = describeManagementError(new ApiError(403, "FORBIDDEN", "No access."));
    expect(info.title).toBe("Access restricted");
    expect(info.retryable).toBe(false);

    const emailInfo = describeManagementError(
      new ApiError(
        403,
        "FORBIDDEN",
        "Email search is restricted to event administrators.",
      ),
    );
    expect(emailInfo.description).toBe(
      "Email search is restricted to event administrators.",
    );
  });

  it("maps not found, conflict, and validation errors", () => {
    expect(describeManagementError(new ApiError(404, "NOT_FOUND", "Missing.")).title).toBe(
      "Not found",
    );
    expect(
      describeManagementError(new ApiError(409, "CONFLICT", "Already checked in.")),
    ).toMatchObject({ title: "Conflict", description: "Already checked in." });
    expect(
      describeManagementError(new ApiError(422, "VALIDATION_ERROR", "Invalid slug.")),
    ).toMatchObject({ title: "Invalid request", description: "Invalid slug." });
  });

  it("maps rate limits with retry hints", () => {
    const error = new ApiError(429, "TOO_MANY_REQUESTS", "Slow down.", [
      { retry_after_seconds: 30 },
    ]);
    const info = describeManagementError(error);
    expect(info.title).toBe("Too many requests");
    expect(info.description).toContain("30 seconds");
    expect(info.retryable).toBe(true);
  });

  it("maps network and unexpected errors", () => {
    expect(describeManagementError(new TypeError("Failed to fetch")).title).toBe(
      "Network error",
    );
    expect(describeManagementError(new Error("gateway exploded")).title).toBe(
      "Network error",
    );
    expect(describeManagementError(new ApiError(500, "INTERNAL_SERVER_ERROR", "Oops")).retryable).toBe(
      true,
    );
    expect(describeManagementError({ unknown: true }).retryable).toBe(true);
  });
});

describe("validationFieldErrors", () => {
  it("extracts backend validation details by field", () => {
    const error = new ApiError(422, "VALIDATION_ERROR", "Invalid request", [
      { loc: ["body", "name"], msg: "Name is required." },
      { loc: ["query", "page"], msg: "Page must be positive." },
    ]);
    expect(validationFieldErrors(error)).toEqual({
      name: "Name is required.",
      page: "Page must be positive.",
    });
  });

  it("returns an empty map for non-validation errors", () => {
    expect(validationFieldErrors(new Error("nope"))).toEqual({});
    expect(validationFieldErrors(new ApiError(409, "CONFLICT", "Conflict"))).toEqual({});
  });
});
