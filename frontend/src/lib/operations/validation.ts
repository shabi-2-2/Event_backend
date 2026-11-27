import type { DownloadedFile } from "@/lib/api/client";
import type {
  AuditLogRecord,
  EmailDeliveryRecord,
  EmailDeliveryStatus,
  EmailPurpose,
  EmailRetryResponse,
  ExportFormat,
  Page,
} from "@/lib/api/contracts";

const EMAIL_STATUSES: readonly EmailDeliveryStatus[] = [
  "pending",
  "sent",
  "failed",
  "dead_letter",
];

const EMAIL_PURPOSES: readonly EmailPurpose[] = [
  "ticket_issued",
  "ticket_reissued",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPageShape<T>(
  value: unknown,
  isItem: (item: unknown) => item is T,
): value is Page<T> {
  if (!isRecord(value)) {
    return false;
  }

  return (
    Array.isArray(value.items) &&
    value.items.every(isItem) &&
    typeof value.page === "number" &&
    typeof value.page_size === "number" &&
    typeof value.total === "number"
  );
}

function isEmailDelivery(value: unknown): value is EmailDeliveryRecord {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.delivery_reference === "string" &&
    typeof value.registration_reference === "string" &&
    typeof value.ticket_reference === "string" &&
    typeof value.purpose === "string" &&
    EMAIL_PURPOSES.includes(value.purpose as EmailPurpose) &&
    typeof value.status === "string" &&
    EMAIL_STATUSES.includes(value.status as EmailDeliveryStatus) &&
    typeof value.attempts === "number" &&
    typeof value.resend_sequence === "number" &&
    (value.error_code === null || typeof value.error_code === "string") &&
    (value.next_attempt_at === null || typeof value.next_attempt_at === "string") &&
    typeof value.created_at === "string" &&
    (value.sent_at === null || typeof value.sent_at === "string")
  );
}

function isAuditContext(
  value: unknown,
): value is AuditLogRecord["context"] {
  if (!isRecord(value)) {
    return false;
  }

  return Object.values(value).every(
    (entry) =>
      entry === null ||
      typeof entry === "string" ||
      typeof entry === "number" ||
      typeof entry === "boolean",
  );
}

function isAuditLog(value: unknown): value is AuditLogRecord {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.audit_reference === "string" &&
    typeof value.action === "string" &&
    typeof value.target_type === "string" &&
    (value.target_id === null || typeof value.target_id === "string") &&
    isAuditContext(value.context) &&
    (value.actor_user_id === null || typeof value.actor_user_id === "string") &&
    typeof value.created_at === "string"
  );
}

/** Reject unexpected list payloads without logging delivery metadata. */
export function parseEmailDeliveryPage(value: unknown): Page<EmailDeliveryRecord> | null {
  return isPageShape(value, isEmailDelivery) ? value : null;
}

/** Reject unexpected retry payloads without logging delivery metadata. */
export function parseEmailRetryResponse(value: unknown): EmailRetryResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  const valid =
    typeof value.delivery_reference === "string" &&
    typeof value.registration_reference === "string" &&
    typeof value.ticket_reference === "string" &&
    typeof value.status === "string" &&
    EMAIL_STATUSES.includes(value.status as EmailDeliveryStatus) &&
    typeof value.resend_sequence === "number" &&
    typeof value.previous_status === "string" &&
    EMAIL_STATUSES.includes(value.previous_status as EmailDeliveryStatus) &&
    typeof value.message === "string";

  return valid ? (value as unknown as EmailRetryResponse) : null;
}

/** Reject unexpected audit payloads without logging context values. */
export function parseAuditLogPage(value: unknown): Page<AuditLogRecord> | null {
  return isPageShape(value, isAuditLog) ? value : null;
}

const EXPORT_CONTENT_TYPES: Record<ExportFormat, string> = {
  csv: "text/csv",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};

/** Verifies backend file metadata before saving it in the browser. */
export function parseDownloadedFile(
  value: unknown,
  format: ExportFormat,
): DownloadedFile | null {
  if (!isRecord(value)) {
    return null;
  }

  const contentType =
    typeof value.contentType === "string" ? value.contentType.toLowerCase() : null;
  const valid =
    value.blob instanceof Blob &&
    typeof value.filename === "string" &&
    value.filename.trim().length > 0 &&
    contentType !== null &&
    contentType.startsWith(EXPORT_CONTENT_TYPES[format]);

  return valid ? (value as unknown as DownloadedFile) : null;
}
