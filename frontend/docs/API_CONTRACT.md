# Backend API Contract (verified from source)

This document records only contracts that exist in the FastAPI backend at repository HEAD `c7bc17e`. It was derived from `README.md`, `app/main.py`, `app/api/router.py`, `app/api/v1/*.py`, `app/security/*.py`, `app/core/*.py`, `app/schemas/*.py`, and the relevant tests.

The frontend must not invent endpoints, roles, permissions, fields, or response shapes beyond this document.

## Base URLs and health

The backend mounts:

- Root router with no prefix.
- Versioned routers under `settings.api_prefix`, which defaults to `/api/v1`.

| Method | Path | Auth | Success | Response |
|---|---|---:|---:|---|
| `GET` | `/health` | No | `200` | `{ status: "healthy", service: string }` |
| `GET` | `/api/v1/health` | No | `200` | `{ status: "healthy", service: string, api_version: "v1", app_version: string }` |
| `GET` | `/api/v1/ready` | No | `200` | `{ status: "ready", checks: { database: "ready" } }` |
| `GET` | `/api/v1/ready` | No | `503` | `{ status: "not_ready", checks: { database: "unavailable" } }` |

`GET /docs`, `GET /redoc`, and `GET /openapi.json` exist only when `EVENT_DOCS_ENABLED=true` (default). Production may disable them.

## Authentication

There are no login, signup, logout, refresh, `/me`, or role endpoints in this backend. Supabase Auth is the identity provider. The frontend sends the Supabase access token as:

```http
Authorization: Bearer <supabase-access-token>
```

`get_current_user` requires exactly two whitespace-separated header parts and a case-insensitive `bearer` scheme. Missing or malformed headers produce:

```json
{ "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired credentials." } }
```

### JWT verification

Required claims: `sub`, `exp`, `iat`, `iss`, `aud`.

- HS256 uses `EVENT_SUPABASE_JWT_SECRET`.
- JWKS uses `EVENT_SUPABASE_JWKS_URL` or the derived `${EVENT_SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
- Issuer defaults to `${EVENT_SUPABASE_URL}/auth/v1`; explicit `EVENT_JWT_ISSUER` wins.
- Audience defaults to `authenticated`.
- `sub` must parse as a UUID.
- Internal failure reasons are logged only; every failure returns the same generic `401 UNAUTHORIZED` envelope.

### Roles and permissions

The backend never trusts `role`, `roles`, `app_metadata`, or `user_metadata` JWT claims. It resolves roles by querying `staff_memberships` using the verified `sub` and the event resolved from `event_slug`.

Exact `Permission` values and role map:

| Permission | `admin` | `checkin` | `viewer` |
|---|---:|---:|---:|
| `event.manage` | Yes | No | No |
| `attendee.manage` | Yes | No | No |
| `ticket.manage` | Yes | No | No |
| `attendance.export` | Yes | No | No |
| `staff.manage` | Yes | No | No |
| `ticket.verify` | Yes | Yes | No |
| `ticket.checkin` | Yes | Yes | No |
| `attendee.view` | Yes | No | Yes |
| `attendee.view.checkin` | Yes | Yes | No |
| `event.stats.view` | Yes | No | Yes |
| `registration.manage` | Yes | No | No |
| `email_delivery.view` | Yes | No | No |
| `email_delivery.manage` | Yes | No | No |
| `audit.view` | Yes | No | No |

`StaffRole` values are `admin`, `checkin`, and `viewer`. `attendee.manage` and `attendee.view.checkin` exist in the RBAC map but are not used by any current endpoint. Unknown permissions default deny.

`GET`/`POST /api/v1/admin/events` use a global permission check: the user must have `admin` on at least one event. All other admin endpoints are event-scoped. An unknown event slug returns `403 FORBIDDEN`, not `404`, for event-scoped endpoints.

## Error envelope

All ordinary API errors use:

```ts
type ErrorResponse = {
  error: {
    code: string;
    message: string;
    details?: Array<Record<string, unknown>>;
  };
};
```

`details` is omitted when absent; it is never emitted as `null`.

Status/code mapping:

| Status | Code | Default message |
|---:|---|---|
| `400` | `BAD_REQUEST` | The request could not be understood. |
| `401` | `UNAUTHORIZED` | Authentication is required. |
| `403` | `FORBIDDEN` | You do not have access to this resource. |
| `404` | `NOT_FOUND` | The requested resource was not found. |
| `405` | `METHOD_NOT_ALLOWED` | This method is not allowed for the resource. |
| `409` | `CONFLICT` | The request conflicts with the current state. |
| `422` | `VALIDATION_ERROR` | Request validation failed. |
| `429` | `TOO_MANY_REQUESTS` | Too many requests. Please retry later. |
| other HTTP | `HTTP_ERROR` | The request could not be completed. |
| unhandled | `INTERNAL_SERVER_ERROR` | An unexpected error occurred. |

Custom codes used by admin endpoints: `SLUG_CONFLICT`, `FINAL_ADMIN`, and `RESEND_ALREADY_PENDING`.

Validation details are normalized to:

```ts
Array<{ loc: string[]; msg: string; type: string }>
```

No submitted `input` or `ctx` is reflected. Rate-limit `429` details contain:

```ts
Array<{ retry_after_seconds: number }>
```

Every response includes `X-Correlation-ID`, but CORS does not expose that header to browser JavaScript.

## Pagination

`Page[T]` is:

```ts
{
  items: T[];
  page: number;
  page_size: number;
  total: number;
}
```

Constraints: `page >= 1`, `1 <= page_size <= 100`, default `page_size = 50`. There is no cursor, `has_more`, or links field.

## CORS

`EVENT_CORS_ORIGINS` is a comma-separated allow-list; default is empty.

- `allow_credentials` is enabled only when origins are configured.
- Methods: `GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS`.
- Headers: `Authorization`, `Content-Type`, `X-Correlation-ID`.
- No wildcard origin.
- No `Access-Control-Expose-Headers`, so do not rely on reading `X-Correlation-ID` from cross-origin browser code.

## Event endpoints

All event endpoints require `event.manage`. Listing and creation use the global check; the rest are event-scoped.

### `POST /api/v1/admin/events` — `201`

Request (`EventCreate`, `extra="forbid"`):

| Field | Type | Constraints |
|---|---|---|
| `slug` | `string` | 3–100 chars; trimmed and lowercased; `^[a-z0-9]+(?:-[a-z0-9]+)*$` |
| `name` | `string` | 1–200 chars, trimmed |
| `description` | `string \| null` | default `null`, max 5000 |
| `starts_at` | aware datetime | required |
| `ends_at` | aware datetime | required |
| `timezone` | `string` | 1–64 chars, valid `ZoneInfo` name |
| `venue` | `string \| null` | default `null`, max 200; empty string becomes `null` |
| `capacity` | `integer \| null` | default `null`, 1–1,000,000 |
| `registration_opens_at` | aware datetime \| null | default `null` |
| `registration_closes_at` | aware datetime \| null | default `null` |

Timeline rules: `ends_at > starts_at`; `registration_opens_at < starts_at`; `registration_closes_at <= starts_at`; `registration_closes_at > registration_opens_at` when both are supplied.

Success response is `EventResponse`. Errors: `401`, `403`, `409 SLUG_CONFLICT`, `422`, `500`.

### `GET /api/v1/admin/events` — `200`

Query parameters:

- `page`: integer, default `1`, `>= 1`
- `page_size`: integer, default `50`, `1–100`
- `status`: `EventStatus | null`, default `null`

Response: `Page[EventResponse]`. Errors: `401`, `403`, `422`, `500`.

### `EventResponse` (exact fields)

```ts
{
  slug: string;
  name: string;
  description: string | null;
  starts_at: string; // ISO 8601
  ends_at: string;
  timezone: string;
  venue: string | null;
  capacity: number | null;
  registration_opens_at: string | null;
  registration_closes_at: string | null;
  status: "draft" | "published" | "archived" | "cancelled";
  created_at: string;
  updated_at: string;
}
```

There is no numeric `id` field. Ordering for the list is `created_at DESC`, then `slug ASC`.

### `GET /api/v1/admin/events/{event_slug}` — `200`

Returns `EventResponse`. Errors: `401`, `403` (including unknown slug), `404`, `500`.

### `PATCH /api/v1/admin/events/{event_slug}` — `200`

Request (`EventUpdate`, `extra="forbid"`) accepts only these optional fields:

```text
name, description, starts_at, ends_at, timezone, venue, capacity,
registration_opens_at, registration_closes_at
```

`slug` and `status` are rejected with `422`. Timeline validation is re-run after merging. Success returns `EventResponse`. Errors: `401`, `403`, `404`, `422`, `500`.

### Lifecycle endpoints

| Method | Path | Success | Behavior |
|---|---|---:|---|
| `POST` | `/api/v1/admin/events/{event_slug}/publish` | `200` | Only `draft -> published`; otherwise `409 CONFLICT` |
| `POST` | `/api/v1/admin/events/{event_slug}/archive` | `200` | Only `published -> archived`; otherwise `409 CONFLICT` |

Both return `EventResponse`. Archived events cannot be reopened.

## Staff endpoints

All staff endpoints require event-scoped `staff.manage`, which only the `admin` role has. `user_id` is a Supabase `auth.users` UUID; the backend does not create auth accounts.

### `GET /api/v1/admin/events/{event_slug}/staff` — `200`

Query: `page`, `page_size`, `role` (`admin | checkin | viewer`). Response: `Page[StaffResponse]`.

```ts
{
  user_id: string; // UUID
  role: "admin" | "checkin" | "viewer";
  created_at: string;
}
```

Ordering: `created_at ASC`, then `user_id ASC`.

### `POST /api/v1/admin/events/{event_slug}/staff` — `201`

Body: `{ user_id: string, role: StaffRole }`. Returns `StaffResponse`. Duplicate membership returns `409 CONFLICT`. Invalid UUID returns `422`.

### `PATCH /api/v1/admin/events/{event_slug}/staff/{user_id}` — `200`

Body: `{ role: StaffRole }`. Returns `StaffResponse`. Missing membership returns `404`; demoting the final admin returns `409 FINAL_ADMIN`.

### `DELETE /api/v1/admin/events/{event_slug}/staff/{user_id}` — `204`

Empty body. Missing membership returns `404`; removing the final admin returns `409 FINAL_ADMIN`.

## Event-scoped admin endpoints (reference)

### Attendees — `attendee.view` (`admin`, `viewer`)

| Method | Path | Success |
|---|---|---:|
| `GET` | `/api/v1/admin/events/{event_slug}/attendees` | `200 Page[AdminAttendeeResponse \| ViewerAttendeeResponse]` |
| `GET` | `/api/v1/admin/events/{event_slug}/attendees/{attendee_reference}` | `200` role-specific response |

Query for the list: `page`, `page_size`, `search` (≤200), `urn` (≤64 exact, case-insensitive), `email` (≤255 partial, admin only), `registration_status`, `ticket_status`, `check_in_status`, `sort_by` (`registered_at | name`), `sort_order` (`asc | desc`). A viewer supplying `email` receives `403 FORBIDDEN`.

`AdminAttendeeResponse` fields:

```text
attendee_reference, full_name, urn, email, phone, registration_reference,
registration_status, registered_at, checked_in_at, cancelled_at,
ticket_reference, ticket_status, ticket_expires_at, ticket_used_at,
check_in_status, check_in_at, station
```

`ViewerAttendeeResponse` has exactly seven fields:

```text
attendee_reference, full_name, urn, registration_status,
ticket_status, check_in_status, checked_in_at
```

### Registrations — `registration.manage` (`admin`)

| Method | Path | Success |
|---|---|---:|
| `GET` | `/api/v1/admin/events/{event_slug}/registrations` | `200 Page[RegistrationResponse]` |
| `GET` | `/api/v1/admin/events/{event_slug}/registrations/{registration_reference}` | `200 RegistrationResponse` |
| `POST` | `/api/v1/admin/events/{event_slug}/registrations/{registration_reference}/cancel` | `200 RegistrationResponse` |

List query: `page`, `page_size`, `reference`, `name`, `email`, `registration_status`, `ticket_status`, `check_in_status`.

`RegistrationResponse` fields:

```text
registration_reference, attendee_reference, attendee_name, email, phone,
registration_status, registered_at, checked_in_at, cancelled_at,
ticket_reference, ticket_status, check_in_status, check_in_at, station
```

### Tickets — `ticket.manage` (`admin`)

| Method | Path | Success |
|---|---|---:|
| `GET` | `/api/v1/admin/events/{event_slug}/tickets` | `200 Page[TicketResponse]` |
| `POST` | `/api/v1/admin/events/{event_slug}/tickets/{ticket_reference}/revoke` | `200 TicketResponse` |
| `POST` | `/api/v1/admin/events/{event_slug}/tickets/{ticket_reference}/resend` | `200 TicketResendResponse` |

List query: `page`, `page_size`, `ticket_status`, `reference`.

`TicketResponse` fields:

```text
ticket_reference, attendee_reference, attendee_name, registration_status,
ticket_status, issued_at, expires_at, used_at, revoked_at, check_in_at
```

`TicketResendResponse` fields: `ticket_reference`, `delivery_reference`, `status`, `resend_sequence`, `message`.

### Analytics — `event.stats.view` (`admin`, `viewer`)

| Path | Query | Response fields |
|---|---|---|
| `.../analytics/overview` | none | `total_registrations`, `confirmed_registrations`, `cancelled_registrations`, `declined_rsvps`, `checked_in_attendees`, `not_checked_in_attendees`, `active_tickets`, `used_tickets`, `revoked_tickets`, `expired_tickets`, `pending_email_deliveries`, `sent_email_deliveries`, `failed_email_deliveries`, `dead_letter_email_deliveries` |
| `.../analytics/registrations` | `from_date`, `to_date` | `granularity`, `from_date`, `to_date`, `buckets`, `total_in_range` |
| `.../analytics/attendance` | `from_date`, `to_date` | `confirmed_registrations`, `checked_in_attendees`, `not_checked_in_attendees`, `attendance_percentage`, `buckets` |
| `.../analytics/email-deliveries` | none | `total_deliveries`, `status_counts`, `attempt_summary` |

`TimeBucket` is `{ period_start: string, period: "day" | "week" | "month", count: number }`. Dates must be timezone-aware and span at most 3660 days.

### Exports — `attendance.export` (`admin`)

| Path | Content type |
|---|---|
| `.../exports/attendees.csv` | `text/csv; charset=utf-8` |
| `.../exports/attendees.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `.../exports/checkins.csv` | `text/csv; charset=utf-8` |
| `.../exports/checkins.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

Responses are binary streams with `Content-Disposition: attachment; filename="..."`. Rate scope is `admin_export` (default 10 per window). `429` details include `retry_after_seconds`.

### Audit logs — `audit.view` (`admin`)

`GET .../audit-logs` returns `Page[AuditLogResponse]`. Query: `page`, `page_size`, `action`, `actor_user_id`, `from_date`, `to_date`, `sort_order`.

`AuditLogResponse` fields:

```text
audit_reference (UUID), action, target_type, target_id (string | null),
context (object), actor_user_id (UUID | null), created_at
```

### Email deliveries — `email_delivery.view` / `email_delivery.manage` (`admin`)

`GET .../email-deliveries` returns `Page[EmailDeliveryResponse]`. Query: `page`, `page_size`, `status`, `registration_reference`, `ticket_reference`, `min_attempts`, `max_attempts`, `error_code`, `next_attempt_before`, `next_attempt_after`.

`EmailDeliveryResponse` fields:

```text
delivery_reference (UUID), registration_reference, ticket_reference,
purpose, status, attempts, resend_sequence, error_code,
next_attempt_at, created_at, sent_at
```

`POST .../email-deliveries/{delivery_reference}/retry` returns `EmailRetryResponse` with `delivery_reference`, `registration_reference`, `ticket_reference`, `status`, `resend_sequence`, `previous_status`, `message`. Only `failed` or `dead_letter` deliveries are retryable.

## Scanner endpoints

| Method | Path | Permission | Rate scope |
|---|---|---|---|
| `POST` | `/api/v1/events/{event_slug}/checkins/verify` | `ticket.verify` | `checkin_verify` (120/window default) |
| `POST` | `/api/v1/events/{event_slug}/checkins/confirm` | `ticket.checkin` | `checkin_confirm` (60/window default) |

Request:

```ts
{
  ticket_token: string; // 20–256 chars after trim
  station?: string | null; // confirm only, ≤100, optional
}
```

Every business outcome is HTTP `200`:

```ts
{
  success: boolean;
  outcome:
    | "valid_ticket"
    | "checked_in"
    | "already_checked_in"
    | "invalid_ticket"
    | "revoked_ticket"
    | "expired_ticket"
    | "registration_cancelled"
    | "invalid_registration_state";
  message: string;
  ticket: {
    attendee_name: string;
    urn: string;
    ticket_status: string;
    registration_status: string;
    check_in_status: string;
  } | null;
}
```

`invalid_ticket` always has `ticket: null`. `verify` is read-only; `confirm` mutates state.

## Webhook endpoint

`POST /api/v1/webhooks/google-forms` uses HMAC headers `X-Webhook-Key-Id`, `X-Webhook-Timestamp`, and `X-Webhook-Signature`, not Supabase auth.

Request fields: `event_slug`, `submission_id`, `name`, `email`, `phone`, `urn`, `attendance` (`yes | no`).

Response shape: `{ success: boolean, outcome: string, submission_id: string, message: string }`. HTTP mapping: `registered -> 201`, `rejected_validation -> 422` with the webhook response shape (not the error envelope), all other outcomes `200`. Auth and rate-limit failures use the standard error envelope.

## Exact enum values

| Enum | Values |
|---|---|
| `EventStatus` | `draft`, `published`, `archived`, `cancelled` |
| `RegistrationStatus` | `registered`, `checked_in`, `cancelled` |
| `TicketStatus` | `active`, `used`, `revoked`, `expired` |
| `CheckinFilterStatus` | `pending`, `checked_in` |
| `CheckinStatus` | `pending`, `checked_in` |
| `CheckinSource` | `mobile`, `admin` |
| `EmailDeliveryStatus` | `pending`, `sent`, `failed`, `dead_letter` |
| `EmailPurpose` | `ticket_issued`, `ticket_reissued` |
| `StaffRole` | `admin`, `checkin`, `viewer` |
| `AttendeeSortField` | `registered_at`, `name` |
| `SortOrder` | `asc`, `desc` |
| `AnalyticsGranularity` | `day`, `week`, `month` |
| `ExportFormat` | `csv`, `xlsx` |
| `RateLimitScope` | `webhook`, `checkin_verify`, `checkin_confirm`, `admin_export` |

## Frontend assumptions to avoid

1. Do not call backend auth endpoints; none exist.
2. Do not infer roles or permissions from JWT claims.
3. Do not expose service-role keys, database URLs, webhook secrets, or JWT secrets in frontend code or configuration.
4. Do not use internal numeric IDs in URLs. Public references are event `slug`, attendee/registration `urn`, ticket `ticket_code`, staff `user_id`, audit `audit_reference`, and delivery `delivery_reference`.
5. Do not assume no-op mutations create duplicate audit records.
6. Do not assume `PATCH` can change `slug` or `status`.
7. Do not assume unknown event slugs return `404`; event-scoped endpoints return `403`.
8. Do not treat scanner/webhook `success=false` as an HTTP error; those business outcomes are `200`.
9. Do not rely on `/openapi.json` or `X-Correlation-ID` being browser-readable in production.
