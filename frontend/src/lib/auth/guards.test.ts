import { describe, expect, it } from "vitest";
import {
  loginRedirectFor,
  requireAuthenticatedUser,
  safeNextPath,
} from "@/lib/auth/guards";

describe("protected route helpers", () => {
  it("accepts internal next paths and rejects external redirects", () => {
    expect(safeNextPath("/events?event=demo")).toBe("/events?event=demo");
    expect(safeNextPath("//evil.example")).toBe("/dashboard");
    expect(safeNextPath("https://evil.example")).toBe("/dashboard");
    expect(safeNextPath(["/dashboard"])).toBe("/dashboard");
  });

  it("redirects unauthenticated users to login with a safe next path", () => {
    expect(requireAuthenticatedUser(null, "/events")).toBe("/login?next=%2Fevents");
    expect(requireAuthenticatedUser({ id: "user-1" }, "/events")).toBeNull();
  });

  it("includes session expiry reason when required", () => {
    expect(loginRedirectFor("/dashboard", "session_expired")).toBe(
      "/login?next=%2Fdashboard&reason=session_expired",
    );
  });
});
