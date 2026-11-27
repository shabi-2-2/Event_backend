import { describe, expect, it } from "vitest";
import {
  isStationValid,
  isTicketTokenValid,
  normalizeStation,
  normalizeTicketToken,
} from "@/lib/scanner/token";

describe("scanner token normalization", () => {
  it("accepts only raw tokens in the backend length range after trimming", () => {
    expect(normalizeTicketToken("  raw-token-1234567890  ")).toBe("raw-token-1234567890");
    expect(isTicketTokenValid("  raw-token-1234567890  ")).toBe(true);
    expect(isTicketTokenValid("short")).toBe(false);
    expect(isTicketTokenValid("x".repeat(257))).toBe(false);
  });

  it("normalizes station whitespace to null", () => {
    expect(normalizeStation("  ")).toBeNull();
    expect(normalizeStation(" Door 1 ")).toBe("Door 1");
    expect(isStationValid("  ")).toBe(true);
  });

  it("rejects station characters outside the backend pattern", () => {
    expect(isStationValid("Door 1")).toBe(true);
    expect(isStationValid("Door/1")).toBe(false);
    expect(isStationValid("x".repeat(101))).toBe(false);
  });
});
