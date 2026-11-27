export type EventStatus = "draft" | "published" | "archived" | "cancelled";
export type StaffRole = "admin" | "checkin" | "viewer";
export type RegistrationStatus = "registered" | "checked_in" | "cancelled";
export type TicketStatus = "active" | "used" | "revoked" | "expired";
export type CheckinStatus = "pending" | "checked_in";
export type SortOrder = "asc" | "desc";
export type AttendeeSortField = "registered_at" | "name";
export type EmailDeliveryStatus = "pending" | "sent" | "failed" | "dead_letter";
export type AnalyticsGranularity = "day" | "week" | "month";

export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type PaginationParams = {
  page?: number;
  page_size?: number;
};

/** Exact public event response fields from `app/schemas/admin.py`. */
export type EventRecord = {
  slug: string;
  name: string;
  description: string | null;
  starts_at: string;
  ends_at: string;
  timezone: string;
  venue: string | null;
  capacity: number | null;
  registration_opens_at: string | null;
  registration_closes_at: string | null;
  status: EventStatus;
  created_at: string;
  updated_at: string;
};

export type ListEventsParams = PaginationParams & {
  status?: EventStatus;
};

export type StaffRecord = {
  user_id: string;
  role: StaffRole;
  created_at: string;
};

export type ValidationIssue = {
  loc?: unknown;
  msg?: string;
  type?: string;
  [key: string]: unknown;
};

/** Exact `TimeBucket` response shape from `app/schemas/admin.py`. */
export type TimeBucket = {
  period_start: string;
  period: AnalyticsGranularity;
  count: number;
};

/** Exact fields from `OverviewAnalyticsResponse`. */
export type OverviewAnalyticsResponse = {
  total_registrations: number;
  confirmed_registrations: number;
  cancelled_registrations: number;
  declined_rsvps: number;
  checked_in_attendees: number;
  not_checked_in_attendees: number;
  active_tickets: number;
  used_tickets: number;
  revoked_tickets: number;
  expired_tickets: number;
  pending_email_deliveries: number;
  sent_email_deliveries: number;
  failed_email_deliveries: number;
  dead_letter_email_deliveries: number;
};

export type AnalyticsDateRangeParams = {
  from_date?: string;
  to_date?: string;
};

/** Exact fields from `RegistrationAnalyticsResponse`. */
export type RegistrationAnalyticsResponse = {
  granularity: AnalyticsGranularity;
  from_date: string | null;
  to_date: string | null;
  buckets: TimeBucket[];
  total_in_range: number;
};

/** Exact fields from `AttendanceAnalyticsResponse`. */
export type AttendanceAnalyticsResponse = {
  confirmed_registrations: number;
  checked_in_attendees: number;
  not_checked_in_attendees: number;
  attendance_percentage: number;
  buckets: TimeBucket[];
};

export type EmailDeliveryStatusCounts = Record<EmailDeliveryStatus, number>;

export type EmailAttemptSummary = {
  total_attempts: number;
  max_attempts: number;
  average_attempts: number;
  retried_deliveries: number;
};

/** Exact fields from `EmailAnalyticsResponse`. */
export type EmailAnalyticsResponse = {
  total_deliveries: number;
  status_counts: EmailDeliveryStatusCounts;
  attempt_summary: EmailAttemptSummary;
};
