import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsError } from "@/components/dashboard/analytics-error";
import { ApiError } from "@/lib/api/errors";

describe("AnalyticsError", () => {
  it("maps forbidden responses to a clear access-denied state", () => {
    render(
      <AnalyticsError
        error={new ApiError(403, "FORBIDDEN", "You do not have access to this resource.")}
      />,
    );

    expect(screen.getByText("Access restricted")).toBeInTheDocument();
    expect(screen.getByText(/analytics access/i)).toBeInTheDocument();
  });

  it("maps validation and rate-limit responses consistently", () => {
    const { rerender } = render(
      <AnalyticsError
        error={
          new ApiError(422, "VALIDATION_ERROR", "Request validation failed.", [
            { loc: ["query", "to_date"], msg: "to_date must not be before from_date.", type: "value_error" },
          ])
        }
      />,
    );

    expect(screen.getByText("Invalid date range")).toBeInTheDocument();
    expect(screen.getByText(/must not be before from_date/)).toBeInTheDocument();

    rerender(
      <AnalyticsError
        error={
          new ApiError(429, "TOO_MANY_REQUESTS", "Too many requests.", [
            { retry_after_seconds: 30 },
          ])
        }
      />,
    );

    expect(screen.getByText("Too many requests")).toBeInTheDocument();
    expect(screen.getByText(/retry in 30 seconds/)).toBeInTheDocument();
  });

  it("offers a retry action", () => {
    const onRetry = vi.fn();
    render(<AnalyticsError error={new Error("Network failure")} onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
