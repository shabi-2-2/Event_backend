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
