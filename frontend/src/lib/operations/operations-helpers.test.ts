import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AuditLogRecord,
  EmailDeliveryRecord,
  EmailRetryResponse,
} from "@/lib/api/contracts";
import {
  datetimeLocalToUtc,
  isUuid,
  parseAttemptFilter,
} from "@/lib/operations/filters";
import {
  safeDownloadFilename,
  triggerBrowserDownload,
} from "@/lib/operations/download";
import {
  parseAuditLogPage,
  parseDownloadedFile,
  parseEmailDeliveryPage,
  parseEmailRetryResponse,
} from "@/lib/operations/validation";

const delivery: EmailDeliveryRecord = {
  delivery_reference: "del-1",
  registration_reference: "reg-1",
  ticket_reference: "tkt-1",
  purpose: "ticket_issued",
  status: "failed",
  attempts: 2,
  resend_sequence: 0,
  error_code: "SMTP_TIMEOUT",
  next_attempt_at: null,
  created_at: "2026-06-01T10:00:00Z",
  sent_at: null,
};

const retry: EmailRetryResponse = {
  delivery_reference: "del-1",
  registration_reference: "reg-1",
  ticket_reference: "tkt-1",
  status: "pending",
  resend_sequence: 1,
  previous_status: "failed",
  message: "Replacement job queued.",
};

const audit: AuditLogRecord = {
  audit_reference: "aud-1",
  action: "ticket.revoked",
  target_type: "ticket",
  target_id: "tkt-1",
  context: { from_status: "active", to_status: "revoked", sequence: 2 },
  actor_user_id: "11111111-1111-4111-8111-111111111111",
  created_at: "2026-06-01T10:00:00Z",
};

describe("operation filters and download helpers", () => {
  it("converts datetime-local values to timezone-aware UTC strings", () => {
    expect(datetimeLocalToUtc("2026-06-01T08:30")).toBe("2026-06-01T08:30:00.000Z");
    expect(datetimeLocalToUtc("  ")).toBeUndefined();
    expect(datetimeLocalToUtc("not-a-date")).toBeUndefined();
  });

  it("enforces the backend attempt bounds", () => {
    expect(parseAttemptFilter(" 0 ")).toBe(0);
    expect(parseAttemptFilter("20")).toBe(20);
    expect(parseAttemptFilter("-1")).toBeUndefined();
    expect(parseAttemptFilter("21")).toBeUndefined();
    expect(parseAttemptFilter("1.5")).toBeUndefined();
    expect(parseAttemptFilter("")).toBeUndefined();
  });

  it("validates actor UUIDs before sending audit filters", () => {
    expect(isUuid("11111111-1111-4111-8111-111111111111")).toBe(true);
    expect(isUuid("11111111-1111-4111-8111-11111111111g")).toBe(false);
    expect(isUuid("not-a-uuid")).toBe(false);
  });

  it("removes path segments from backend filenames", () => {
    expect(safeDownloadFilename("attendees-summit-2026.csv")).toBe("attendees-summit-2026.csv");
    expect(safeDownloadFilename("../../attendees-summit-2026.csv")).toBe(
      "attendees-summit-2026.csv",
    );
    expect(safeDownloadFilename("..\\checkins-summit-2026.xlsx")).toBe(
      "checkins-summit-2026.xlsx",
    );
    expect(safeDownloadFilename("../", "download")).toBe("download");
  });

  describe("triggerBrowserDownload", () => {
    const createObjectUrl = vi.fn(() => "blob:test");
    const revokeObjectUrl = vi.fn();
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    beforeEach(() => {
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        writable: true,
        value: createObjectUrl,
      });
      Object.defineProperty(URL, "revokeObjectURL", {
        configurable: true,
        writable: true,
        value: revokeObjectUrl,
      });
    });

    afterEach(() => {
      clickSpy.mockRestore();
    });

    it("uses the backend filename and revokes the object URL", () => {
      const blob = new Blob(["attendee_reference,name\n"], { type: "text/csv" });

      triggerBrowserDownload({
        blob,
        filename: "attendees-summit-2026.csv",
        contentType: "text/csv; charset=utf-8",
      });

      expect(createObjectUrl).toHaveBeenCalledWith(blob);
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect((clickSpy.mock.instances[0] as HTMLAnchorElement).download).toBe(
        "attendees-summit-2026.csv",
      );
      expect(revokeObjectUrl).toHaveBeenCalledWith("blob:test");
    });
  });
});

describe("operational response validation", () => {
  it("accepts exact email delivery list payloads and rejects unknown statuses", () => {
    const valid = {
      items: [delivery],
      page: 1,
      page_size: 25,
      total: 1,
    };

    expect(parseEmailDeliveryPage(valid)).toEqual(valid);
    expect(
      parseEmailDeliveryPage({ ...valid, items: [{ ...delivery, status: "queued" }] }),
    ).toBeNull();
    expect(parseEmailDeliveryPage({ ...valid, items: [{ ...delivery, attempts: "2" }] })).toBeNull();
  });

  it("accepts exact retry payloads and rejects malformed responses", () => {
    expect(parseEmailRetryResponse(retry)).toEqual(retry);
    expect(parseEmailRetryResponse({ ...retry, previous_status: "unknown" })).toBeNull();
    expect(parseEmailRetryResponse({ ...retry, message: 42 })).toBeNull();
  });

  it("accepts scalar redacted audit context and rejects nested payloads", () => {
    const valid = {
      items: [audit],
      page: 1,
      page_size: 25,
      total: 1,
    };

    expect(parseAuditLogPage(valid)).toEqual(valid);
    expect(
      parseAuditLogPage({
        ...valid,
        items: [{ ...audit, context: { before: { email: "private@example.com" } } }],
      }),
    ).toBeNull();
  });

  it("verifies export metadata before saving a file", () => {
    const csvFile = {
      blob: new Blob(["a,b\n"], { type: "text/csv" }),
      filename: "attendees-summit-2026.csv",
      contentType: "text/csv; charset=utf-8",
    };
    const xlsxFile = {
      blob: new Blob(["xlsx"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      filename: "checkins-summit-2026.xlsx",
      contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    };

    expect(parseDownloadedFile(csvFile, "csv")).toEqual(csvFile);
    expect(parseDownloadedFile(xlsxFile, "xlsx")).toEqual(xlsxFile);
    expect(parseDownloadedFile({ ...csvFile, contentType: "application/pdf" }, "csv")).toBeNull();
    expect(parseDownloadedFile({ ...xlsxFile, filename: "" }, "xlsx")).toBeNull();
  });
});
