export type EventStatus = "draft" | "published" | "archived" | "cancelled";
export type StaffRole = "admin" | "checkin" | "viewer";
export type RegistrationStatus = "registered" | "checked_in" | "cancelled";
export type TicketStatus = "active" | "used" | "revoked" | "expired";
export type CheckinStatus = "pending" | "checked_in";
export type CheckinOutcome =
  | "valid_ticket"
  | "checked_in"
  | "already_checked_in"
  | "invalid_ticket"
  | "revoked_ticket"
  | "expired_ticket"
  | "registration_cancelled"
  | "invalid_registration_state";
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

/** Backend filter name is `CheckinFilterStatus`; the existing union is identical. */
export type CheckinFilterStatus = CheckinStatus;

/** Exact writable fields from `EventCreate`. */
export type EventCreateRequest = {
  slug: string;
  name: string;
  description?: string | null;
  starts_at: string;
  ends_at: string;
  timezone: string;
  venue?: string | null;
  capacity?: number | null;
  registration_opens_at?: string | null;
  registration_closes_at?: string | null;
};

/** Exact writable fields from `EventUpdate`. `slug` and `status` are forbidden. */
export type EventUpdateRequest = {
  name?: string;
  description?: string | null;
  starts_at?: string;
  ends_at?: string;
  timezone?: string;
  venue?: string | null;
  capacity?: number | null;
  registration_opens_at?: string | null;
  registration_closes_at?: string | null;
};

export type AttendeeListParams = PaginationParams & {
  search?: string;
  urn?: string;
  email?: string;
  registration_status?: RegistrationStatus;
  ticket_status?: TicketStatus;
  check_in_status?: CheckinFilterStatus;
  sort_by?: AttendeeSortField;
  sort_order?: SortOrder;
};

type AttendeeBaseRecord = {
  attendee_reference: string;
  full_name: string;
  urn: string;
  registration_status: RegistrationStatus;
  ticket_status: TicketStatus | null;
  check_in_status: CheckinFilterStatus;
  checked_in_at: string | null;
};

/** Exact fields from `AdminAttendeeResponse`. */
export type AdminAttendeeRecord = AttendeeBaseRecord & {
  email: string;
  phone: string | null;
  registration_reference: string;
  registered_at: string;
  cancelled_at: string | null;
  ticket_reference: string | null;
  ticket_expires_at: string | null;
  ticket_used_at: string | null;
  check_in_at: string | null;
  station: string | null;
};

/** Exact fields from `ViewerAttendeeResponse`. */
export type ViewerAttendeeRecord = AttendeeBaseRecord;

export type AttendeeRecord = AdminAttendeeRecord | ViewerAttendeeRecord;

export type RegistrationListParams = PaginationParams & {
  reference?: string;
  name?: string;
  email?: string;
  registration_status?: RegistrationStatus;
  ticket_status?: TicketStatus;
  check_in_status?: CheckinFilterStatus;
};

/** Exact fields from `RegistrationResponse`. */
export type RegistrationRecord = {
  registration_reference: string;
  attendee_reference: string;
  attendee_name: string;
  email: string;
  phone: string | null;
  registration_status: RegistrationStatus;
  registered_at: string;
  checked_in_at: string | null;
  cancelled_at: string | null;
  ticket_reference: string | null;
  ticket_status: TicketStatus | null;
  check_in_status: CheckinFilterStatus;
  check_in_at: string | null;
  station: string | null;
};

export type TicketListParams = PaginationParams & {
  ticket_status?: TicketStatus;
  reference?: string;
};

/** Exact fields from `TicketResponse`; secrets are never returned. */
export type TicketRecord = {
  ticket_reference: string;
  attendee_reference: string;
  attendee_name: string;
  registration_status: RegistrationStatus;
  ticket_status: TicketStatus;
  issued_at: string;
  expires_at: string | null;
  used_at: string | null;
  revoked_at: string | null;
  check_in_at: string | null;
};

/** Exact fields from `TicketResendResponse`. */
export type TicketResendResponse = {
  ticket_reference: string;
  delivery_reference: string;
  status: EmailDeliveryStatus;
  resend_sequence: number;
  message: string;
};

/** Exact `TicketCheckRequest` body from `app/schemas/checkin.py`. */
export type TicketCheckRequest = {
  ticket_token: string;
};

/** Exact `ConfirmCheckinRequest` body from `app/schemas/checkin.py`. */
export type ConfirmCheckinRequest = TicketCheckRequest & {
  station?: string | null;
};

/** Exact `ScannerTicketInfo` fields; no email, phone, token, hash, or IDs. */
export type ScannerTicketInfo = {
  attendee_name: string;
  urn: string;
  ticket_status: TicketStatus;
  registration_status: RegistrationStatus;
  check_in_status: CheckinStatus;
};

/** Exact `CheckinResponse` shape from `app/schemas/checkin.py`. */
export type CheckinResponse = {
  success: boolean;
  outcome: CheckinOutcome;
  message: string;
  ticket: ScannerTicketInfo | null;
};

export type StaffListParams = PaginationParams & {
  role?: StaffRole;
};

/** Exact fields from `StaffCreateRequest`. */
export type StaffCreateRequest = {
  user_id: string;
  role: StaffRole;
};

/** Exact fields from `StaffRoleUpdate`. */
export type StaffRoleUpdateRequest = {
  role: StaffRole;
};
