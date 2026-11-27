# Event Management Backend

FastAPI foundation for an event management system covering registration, ticketing,
email delivery, and QR check-in.

## Phase 1 scope

Implemented:

- Application factory and FastAPI entry point
- Pydantic Settings with environment validation
- Structured JSON logging with PII redaction
- CORS configuration
- Standard error envelope and global exception handlers
- `/health`, `/api/v1/health`, and `/api/v1/ready`
- SQLAlchemy engine/session factory
- Alembic initialisation (no domain migrations yet)
- Basic CI, linting, type-checking, and test configuration

Admin workflows were added in Phase 7. Dedicated login/password endpoints remain
out of scope because Supabase Auth is used directly. Scanner APIs were added in
Phase 6; ticket issuance and email delivery were added in Phase 5; the
registration webhook was added in Phase 4; JWT verification primitives were added
in Phase 3; database models were added in Phase 2.

## Phase 2 scope

Implemented:

- SQLAlchemy 2.x models for events, attendees, registrations, tickets, check-ins,
  email outbox, webhook ledger, staff memberships, and audit logs
- UUID primary keys, UTC timestamps, PostgreSQL native enums, and JSONB metadata
- Global normalized URN/email uniqueness plus domain-specific unique constraints
- `RESTRICT` foreign keys; no cascading deletes of historical records
- Initial Alembic revision `20261127_0001`
- psycopg v3 pooling with Supabase transaction-pooling compatibility
- Portable SQLite model tests and isolated PostgreSQL schema/migration tests

Admin APIs were added in Phase 7. The check-in API was added in Phase 6; QR
generation, email sending, and the worker were added in Phase 5; the
HMAC-authenticated registration webhook was added in Phase 4; security primitives
were added in Phase 3.

## Phase 3 scope

Implemented as reusable primitives only (no product endpoints):

- HMAC-SHA256 webhook authentication with key-ID rotation and timestamp tolerance
- Supabase JWT verification with HS256 shared secret or rotating JWKS keys
- Event-scoped RBAC backed by `staff_memberships`, exposed as FastAPI dependencies
- Secure ticket-token generation, SHA-256 hashing, and constant-time comparison
- Shared PostgreSQL fixed-window rate limiting for webhook, check-in, and export scopes

Dedicated login endpoints remain out of scope; admin API endpoints were added in
Phase 7. Scanner endpoints were added in Phase 6; QR generation, Resend
integration, and the email worker were added in Phase 5.

## Phase 4 scope

Implemented:

- `POST /api/v1/webhooks/google-forms` using the Phase 3 HMAC dependency and shared webhook rate limiter
- Pydantic RSVP request contract with explicit attendance values and safe normalization
- Transactional service layer for event resolution, availability, capacity, attendee identity, and registration
- Idempotent processing backed by the existing `webhook_events` ledger and database constraints
- Controlled outcomes for registered, declined, duplicate, already registered, validation rejection, event unavailable, capacity reached, and identity conflict

Ticket generation, QR codes, and email delivery were added in Phase 5; scanner
endpoints were added in Phase 6. Admin endpoints and automatic event creation
were added in Phase 7; dedicated login endpoints remain out of scope.

### Google Forms webhook contract

**Endpoint:** `POST /api/v1/webhooks/google-forms`

Required headers:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Webhook-Key-Id` | Configured key ID, for example `v1` |
| `X-Webhook-Timestamp` | Unix timestamp in seconds |
| `X-Webhook-Signature` | Hex-encoded HMAC-SHA256 signature |

Example request body:

```json
{
  "event_slug": "summer-social-2026",
  "submission_id": "form-response-000123",
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "phone": "+1-555-0100",
  "urn": "2026-000123",
  "attendance": "yes"
}
```

The event must already exist in the database. This endpoint never creates events.
The event must be `published`, within its configured registration window, and
below its configured capacity for `yes` responses.

The sender must normalize attendance to exactly `yes` or `no`. Other values are
rejected. The backend additionally trims surrounding whitespace and lowercases
the value before validation, so ` Yes ` is accepted as `yes`. Email is trimmed and
lowercased; URN is trimmed and uppercased; name and phone are trimmed, and an empty
phone becomes `null`. No other URN transformation is applied.

Signing uses the Phase 3 implementation. The signed message is the literal bytes:

```text
{timestamp}.POST./api/v1/webhooks/google-forms.{rawRequestJsonBody}
```

Compute `HMAC-SHA256(sharedSecret, message)` and send the hex digest in
`X-Webhook-Signature`. The exact body string used for signing must be the body
sent. Timestamp tolerance, key IDs, and secrets come from
`EVENT_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` and `EVENT_WEBHOOK_SIGNING_KEYS`.

Example confirmed response (`201 Created`):

```json
{
  "success": true,
  "outcome": "registered",
  "submission_id": "form-response-000123",
  "message": "RSVP registered."
}
```

Example declined response (`200 OK`):

```json
{
  "success": true,
  "outcome": "declined",
  "submission_id": "form-response-000124",
  "message": "Declined RSVP recorded."
}
```

Example duplicate response (`200 OK`):

```json
{
  "success": true,
  "outcome": "duplicate_submission",
  "submission_id": "form-response-000123",
  "message": "Submission already processed."
}
```

Other recorded business outcomes also return `200 OK`: `already_registered`,
`event_unavailable`, `capacity_reached`, and `identity_conflict`. Schema validation
failures return `422 Unprocessable Entity` with outcome `rejected_validation`.
Authentication failures return the standard `401` error envelope from Phase 3,
and rate-limit failures return the standard `429` error envelope. No response
contains attendee personal data, SQL details, signatures, or secrets.

### Apps Script sender configuration

1. Store the key ID and shared secret in Apps Script Script Properties, not in source.
2. Map the actual Google Sheets headers to the JSON contract above. The backend does not know sheet column names.
3. Normalize `attendance` to `yes` or `no` before sending.
4. Serialize the payload once, then use that exact string as both the request body and the signed message.
5. Compute and hex-encode the HMAC signature with `Utilities.computeHmacSha256Signature`.
6. Send `UrlFetchApp.fetch` with `method: 'post'`, `contentType: 'application/json'`, and the three `X-Webhook-*` headers.
7. Log only the response status, outcome, and submission ID; never log the shared secret, signature, or raw payload.
8. To rotate secrets, add a new key ID to `EVENT_WEBHOOK_SIGNING_KEYS`, update the Script Property, then remove the old key after all senders have switched.

No migration was required for Phase 4. The existing `webhook_events` enum and
`error_code` field represent the outcomes without changing schema.

## Phase 5 scope

Implemented:

- Automatic, exactly-once ticket issuance for confirmed registrations
- SHA-256-only credential persistence and in-memory QR generation
- Transactional creation of the ticket and initial `email_deliveries` job with the registration
- A separately executable Resend worker with safe multi-instance job claiming
- Exponential backoff, bounded retries, dead-letter status, and structured PII-free logs
- Professional responsive HTML ticket email with an inline QR attachment

Admin APIs were added in Phase 7. Still not implemented in the backend: frontend
scanner, admin dashboard, and deployment. The backend scanner API was added in
Phase 6. No migration was required for Phase 5: the existing `tickets`,
`email_deliveries`, and webhook-ledger constraints cover the workflow.

### Ticket issuance architecture

```text
POST /api/v1/webhooks/google-forms
  -> HMAC auth + rate limit
  -> single registration transaction:
       attendee -> registration -> ticket (hash only) -> pending email_delivery -> webhook ledger
  -> commit (no external email call)

event-email-worker (separate process)
  -> claim eligible jobs with FOR UPDATE SKIP LOCKED + short committed lease
  -> derive raw token in memory -> generate QR PNG in memory -> render email
  -> Resend POST /emails with Idempotency-Key
  -> separate transaction marks sent / failed with backoff / dead_letter
```

Exactly one ticket is protected by `uq_tickets_registration_id`; exactly one initial
ticket email is protected by `uq_email_deliveries_ticket_purpose`. Repeated webhook
deliveries are stopped earlier by the webhook ledger, but the unique constraints are
the final concurrency safeguard. A failed transaction rolls back the registration,
ticket, email job, and ledger row together.

Registrations created before Phase 5 are backfilled with one ticket when a later
valid webhook identifies the same registration; an existing ticket is never replaced.

### QR token security

The raw QR credential is never written to the database, QR file, or logs.

- `tickets.ticket_code` stores a random public reference (`secrets.token_urlsafe(24)`).
- `tickets.token_hash` stores `SHA-256(raw_token)` only.
- `derive_ticket_token(ticket_code, EVENT_TICKET_TOKEN_DERIVATION_KEY)` recomputes the
  raw token in memory with HMAC-SHA256 so the independent worker can generate the QR.
- The QR payload is exactly that raw token — no email, name, URN, phone, URLs, or metadata.
- QR bytes exist only in a `BytesIO` buffer and are base64-encoded for the email attachment.

The derivation key must be a long random value outside local/test. When
`EVENT_APP_ENV=production`, the local default is rejected at startup. Rotating this
key invalidates previously derived credentials, so treat it as a durable signing key.
Do not confuse the public `ticket_code` with the raw credential; only the derived raw
token should be accepted by future verification endpoints.

### Email worker startup

Install the package, configure `.env`, apply migrations, then start the API and the
worker as separate processes:

```bash
python -m pip install -e ".[dev]"
alembic upgrade head

# Terminal 1
uvicorn app.main:app --reload

# Terminal 2
python -m app.workers.email_worker
# or, after installation:
event-email-worker
```

The worker validates Resend configuration at startup. It polls every
`EVENT_EMAIL_WORKER_POLL_INTERVAL_SECONDS`, claims up to
`EVENT_EMAIL_WORKER_BATCH_SIZE` jobs per pass, and shuts down cleanly on `SIGINT` or
`SIGTERM`. Multiple worker processes/instances may run against the same database.

Jobs are never locked while Resend is called. A claim increments `attempts` and sets a
short `next_attempt_at` lease in a committed transaction. If a worker is killed mid-send,
the lease expires and another worker reclaims the job. Resend's `Idempotency-Key` is
stable per `email_deliveries.id`, preventing a second email when a request is retried
after an ambiguous timeout.

### Resend configuration

Add these to `.env` (placeholders only; never commit real values):

```dotenv
EVENT_RESEND_API_KEY=re_replace_with_resend_api_key
EVENT_RESEND_FROM_EMAIL=tickets@your-verified-domain.example
EVENT_RESEND_FROM_NAME=Event Management
EVENT_TICKET_TOKEN_DERIVATION_KEY=replace-with-32-plus-character-random-secret
```

`EVENT_RESEND_API_KEY` and `EVENT_TICKET_TOKEN_DERIVATION_KEY` use Pydantic `SecretStr`.
The sender domain must be verified in Resend. The email includes the event name,
attendee name, start/end times in the event timezone, venue, description, a ticket
reference, and the QR as both an inline `cid:` image and a PNG attachment. The raw
token never appears as email text.

### Retry and failure behavior

| Setting | Default | Purpose |
|---|---:|---|
| `EVENT_EMAIL_WORKER_MAX_ATTEMPTS` | `5` | Maximum provider attempts before dead-letter |
| `EVENT_EMAIL_RETRY_BACKOFF_INITIAL_SECONDS` | `30` | First retry delay |
| `EVENT_EMAIL_RETRY_BACKOFF_MULTIPLIER` | `2` | Exponential multiplier |
| `EVENT_EMAIL_RETRY_BACKOFF_MAX_SECONDS` | `3600` | Backoff cap |
| `EVENT_EMAIL_WORKER_LEASE_SECONDS` | `60` | Visibility timeout for interrupted jobs |

A failed send sets `status=failed`, a safe `error_code`, and a future `next_attempt_at`.
After the configured maximum attempts, the row becomes `dead_letter` and is no longer
retried automatically. Success sets `status=sent`, `provider_message_id`, and `sent_at`.
Logs contain delivery IDs, attempts, outcomes, and safe error codes only — never
recipient details, tokens, API keys, or provider error bodies.

## Phase 6 scope

Implemented:

- `POST /api/v1/events/{event_slug}/checkins/verify`: read-only QR ticket verification
- `POST /api/v1/events/{event_slug}/checkins/confirm`: atomic QR ticket check-in
- Supabase JWT authentication with event-scoped `ticket.verify` / `ticket.checkin`
  permissions resolved from `staff_memberships`, never from JWT role claims
- Dedicated PostgreSQL-backed rate limits for verification and confirmation
- Existing Phase 3 SHA-256 token hashing; raw tokens are never stored, returned, or logged
- Explicit Pydantic request/response whitelists for scanner payloads
- Controlled outcomes for all normal ticket, registration, and duplicate states
- PostgreSQL row locking plus `uq_checkins_ticket_id` for duplicate/concurrency safety
- Redacted success and denial audit records in the existing `audit_logs` table
- Isolated PostgreSQL tests for transactions, locking, concurrency, auth, and privacy

No migration was required for Phase 6. The existing `checkins`, `tickets`,
`registrations`, and `audit_logs` tables and constraints already cover this workflow.

### Check-in endpoint contracts

| Endpoint | Required permission | Rate-limit scope | Database writes |
|---|---|---|---|
| `POST /api/v1/events/{event_slug}/checkins/verify` | `ticket.verify` | `checkin_verify` | None |
| `POST /api/v1/events/{event_slug}/checkins/confirm` | `ticket.checkin` | `checkin_confirm` | Check-in, ticket, registration, audit log |

Both endpoints require `Authorization: Bearer <supabase-jwt>`. The JWT verifier
validates signature, issuer, audience, and expiry, then resolves the authenticated
user ID only from verified claims. Authorization is a separate lookup against
`staff_memberships` for the requested event slug. `checkin` and `admin` roles are
allowed; `viewer` is denied. A token containing a fabricated `role` claim does not
grant access. An unknown event slug or a user without event membership returns the
standard `403 FORBIDDEN` envelope.

Verification request:

```json
{
  "ticket_token": "REPLACE_WITH_RAW_QR_TOKEN"
}
```

Verification response for an eligible ticket (`200 OK`):

```json
{
  "success": true,
  "outcome": "valid_ticket",
  "message": "Ticket verified.",
  "ticket": {
    "attendee_name": "Example Attendee",
    "urn": "URN-EXAMPLE",
    "ticket_status": "active",
    "registration_status": "registered",
    "check_in_status": "pending"
  }
}
```

Confirmation request:

```json
{
  "ticket_token": "REPLACE_WITH_RAW_QR_TOKEN",
  "station": "Main Gate"
}
```

Confirmation response for a first check-in (`200 OK`):

```json
{
  "success": true,
  "outcome": "checked_in",
  "message": "Check-in confirmed.",
  "ticket": {
    "attendee_name": "Example Attendee",
    "urn": "URN-EXAMPLE",
    "ticket_status": "used",
    "registration_status": "checked_in",
    "check_in_status": "checked_in"
  }
}
```

`station` is optional. When supplied it must be 1–100 characters, start with a
letter or digit, and contain only letters, digits, spaces, `.`, `_`, `:`, or `-`.
An empty or whitespace-only value is treated as absent. Invalid stations return the
standard `422 VALIDATION_ERROR` envelope.

### Scanner outcomes

All domain outcomes below return `200 OK` with a predictable `success`, `outcome`,
`message`, and optional whitelisted `ticket` object.

| Outcome | `success` | Meaning |
|---|---:|---|
| `valid_ticket` | `true` | Verification only; ticket is eligible and no write occurred |
| `checked_in` | `true` | First check-in was committed |
| `already_checked_in` | `false` | Ticket was previously used; state and timestamp are unchanged |
| `invalid_ticket` | `false` | Unknown token or ticket from another event; no ticket details returned |
| `revoked_ticket` | `false` | Ticket status is `revoked` |
| `expired_ticket` | `false` | Ticket has expired or is past `expires_at` |
| `registration_cancelled` | `false` | Registration status is `cancelled` |
| `invalid_registration_state` | `false` | Registration is not eligible for check-in |

A cross-event token returns exactly the same response as an unknown token, with
`"ticket": null`, so a scanner cannot learn whether the credential exists elsewhere.
Authentication failures (`401`), authorization failures (`403`), validation failures
(`422`), rate-limit failures (`429`), and unexpected database failures (`500`) use the
standard error envelope and never echo submitted token values.

Verification is strictly read-only: it does not mark tickets used, create check-ins,
or write audit records. Confirmation is transactional: it resolves the token hash,
locks the `Ticket` and `Registration` rows with `FOR UPDATE`, rechecks for an existing
`Checkin`, creates the check-in, marks the ticket `used`, sets the registration to
`checked_in`, and writes one success audit record. All four writes commit together or
roll back together. `uq_checkins_ticket_id` is the final safeguard; two concurrent
scanners produce exactly one `checked_in` response and one `already_checked_in`
response. Database locks are released before the response is sent.

Successful confirmations write `checkin.confirmed` audit records. Same-event denials
write `checkin.denied` records. Invalid or cross-event tokens are not audited, because
recording them would disclose that the credential was recognized. Audit context
contains only the controlled outcome and the optional station; it never contains
tokens, token hashes, emails, phone numbers, URNs, or other personal fields.

### Scanner privacy rules

Responses are built from explicit Pydantic models rather than ORM serialization.
The only per-attendee fields returned are `attendee_name` and `urn`, plus ticket,
registration, and check-in status. Responses never include email, phone, internal
UUIDs, raw tokens, token hashes, SQL errors, or database metadata. Application logs
contain event/user IDs, outcomes, and safe metadata only — never the submitted token
or its SHA-256 digest.

### Local API testing

Start the API and use a real Supabase JWT plus a matching `staff_memberships` row for
the event. There is no staff-management API in this phase, so local membership setup
requires direct database access.

```bash
export SUPABASE_JWT='replace-with-a-supabase-jwt-for-a-staff-user'

curl -X POST http://127.0.0.1:8000/api/v1/events/summer-social-2026/checkins/verify \
  -H "Authorization: Bearer $SUPABASE_JWT" \
  -H "Content-Type: application/json" \
  -d '{"ticket_token":"REPLACE_WITH_RAW_QR_TOKEN"}'

curl -X POST http://127.0.0.1:8000/api/v1/events/summer-social-2026/checkins/confirm \
  -H "Authorization: Bearer $SUPABASE_JWT" \
  -H "Content-Type: application/json" \
  -d '{"ticket_token":"REPLACE_WITH_RAW_QR_TOKEN","station":"Main Gate"}'
```

The raw token is the exact QR payload. It is not stored in the database; for a local
ticket you can recompute it in memory from its public `ticket_code` and the configured
derivation key:

```bash
RAW_TOKEN="$(python -c 'from app.core.config import get_settings; from app.security.ticket_tokens import derive_ticket_token; print(derive_ticket_token("REPLACE_WITH_TICKET_CODE", get_settings().ticket_token_derivation_key_value()))')"
```

Do not paste real JWTs, raw tokens, or attendee data into source files, logs, or
shared documentation. Rate-limit defaults are `EVENT_CHECKIN_VERIFY_RATE_LIMIT=120`
and `EVENT_CHECKIN_CONFIRM_RATE_LIMIT=60` per `EVENT_RATE_LIMIT_WINDOW_SECONDS`
(default 60), scoped by event and authenticated user.

Run the PostgreSQL check-in tests with an isolated test database:

```bash
export EVENT_APP_ENV=test
export EVENT_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55432/event_test'
export EVENT_TEST_POSTGRES_URL="$EVENT_DATABASE_URL"
python -m pytest tests/test_checkin_api.py -q
```

## Phase 7 scope

Implemented:

- Thin `/api/v1/admin` routers with all business rules in service modules
- Pydantic request/response whitelists; no ORM objects or internal IDs are returned
- Event creation, listing, detail, patch, publish, and archive with lifecycle guards
- Attendee search/list/detail with admin and viewer response schemas and role-aware PII
- Registration listing/detail and safe, transactional, idempotent cancellation
- Ticket listing, auditable revocation, and outbox-only email resend
- Staff membership list/add/role-change/remove with final-admin protection
- SQL-backed analytics for overview, registrations, attendance, and email deliveries
- Streaming CSV/XLSX attendee and check-in exports with formula-injection escaping
- Read-only, redacted audit-log queries with filters and stable ordering
- Email-delivery monitoring and safe retry of failed/dead-letter outbox jobs
- New permissions, event-scoped authorization, global admin authorization, and audits
- PostgreSQL transaction/locking/concurrency tests with mocked JWT authentication

There are still no login, password, signup, or token-issuance endpoints. Supabase
Auth remains the only identity provider. The frontend scanner, admin dashboard,
and deployment remain out of scope.

Revision `20261127_0003` adds `email_deliveries.resend_sequence`, replaces the
`(ticket_id, purpose)` unique constraint with
`(ticket_id, purpose, resend_sequence)`, and adds the
`ix_webhook_events_event_slug_outcome` analytics index. The downgrade reverses all
three changes. Initial issuance jobs use sequence `0`; resends and retries create
new rows with increasing sequences and never overwrite historical records.
`openpyxl>=3.1,<4.0` was added for XLSX generation.

### Staff onboarding and first-admin bootstrap

Staff users must already exist in Supabase Auth. The `user_id` accepted by the
staff API is the UUID from `auth.users` (visible in the Supabase dashboard); this
API does not create or modify auth accounts.

Event creation and listing are global administrative operations. Because they
cannot be scoped to an existing event slug, they require an `admin` membership on
at least one event. Seed the first event and/or first admin directly, then use the
APIs for everything else:

```sql
-- Replace both placeholders with real UUIDs. The user must exist in auth.users.
INSERT INTO staff_memberships (user_id, event_id, role)
SELECT '00000000-0000-0000-0000-000000000000'::uuid, id, 'admin'::staff_role
FROM events
WHERE slug = 'summer-social-2026';
```

If no event exists yet, insert one event row first, then run the membership
insert. Fabricated JWT role claims are ignored; roles are always read from
`staff_memberships`.

### Endpoint map and permissions

All paths below are prefixed with `/api/v1`. Every endpoint requires
`Authorization: Bearer <supabase-jwt>`. `checkin` users can use the Phase 6
scanner endpoints but no Phase 7 admin endpoint.

| Method | Path | Permission | Allowed roles |
|---|---|---|---|
| `POST` | `/admin/events` | `event.manage` | `admin` on any event (global) |
| `GET` | `/admin/events` | `event.manage` | `admin` on any event (global) |
| `GET` | `/admin/events/{event_slug}` | `event.manage` | `admin` |
| `PATCH` | `/admin/events/{event_slug}` | `event.manage` | `admin` |
| `POST` | `/admin/events/{event_slug}/publish` | `event.manage` | `admin` |
| `POST` | `/admin/events/{event_slug}/archive` | `event.manage` | `admin` |
| `GET` | `/admin/events/{event_slug}/attendees` | `attendee.view` | `admin`, `viewer` |
| `GET` | `/admin/events/{event_slug}/attendees/{urn}` | `attendee.view` | `admin`, `viewer` |
| `GET` | `/admin/events/{event_slug}/registrations` | `registration.manage` | `admin` |
| `GET` | `/admin/events/{event_slug}/registrations/{urn}` | `registration.manage` | `admin` |
| `POST` | `/admin/events/{event_slug}/registrations/{urn}/cancel` | `registration.manage` | `admin` |
| `GET` | `/admin/events/{event_slug}/tickets` | `ticket.manage` | `admin` |
| `POST` | `/admin/events/{event_slug}/tickets/{ticket_code}/revoke` | `ticket.manage` | `admin` |
| `POST` | `/admin/events/{event_slug}/tickets/{ticket_code}/resend` | `ticket.manage` | `admin` |
| `GET` | `/admin/events/{event_slug}/staff` | `staff.manage` | `admin` |
| `POST` | `/admin/events/{event_slug}/staff` | `staff.manage` | `admin` |
| `PATCH` | `/admin/events/{event_slug}/staff/{user_id}` | `staff.manage` | `admin` |
| `DELETE` | `/admin/events/{event_slug}/staff/{user_id}` | `staff.manage` | `admin` |
| `GET` | `/admin/events/{event_slug}/analytics/overview` | `event.stats.view` | `admin`, `viewer` |
| `GET` | `/admin/events/{event_slug}/analytics/registrations` | `event.stats.view` | `admin`, `viewer` |
| `GET` | `/admin/events/{event_slug}/analytics/attendance` | `event.stats.view` | `admin`, `viewer` |
| `GET` | `/admin/events/{event_slug}/analytics/email-deliveries` | `event.stats.view` | `admin`, `viewer` |
| `GET` | `/admin/events/{event_slug}/exports/attendees.csv` | `attendance.export` | `admin` |
| `GET` | `/admin/events/{event_slug}/exports/attendees.xlsx` | `attendance.export` | `admin` |
| `GET` | `/admin/events/{event_slug}/exports/checkins.csv` | `attendance.export` | `admin` |
| `GET` | `/admin/events/{event_slug}/exports/checkins.xlsx` | `attendance.export` | `admin` |
| `GET` | `/admin/events/{event_slug}/audit-logs` | `audit.view` | `admin` |
| `GET` | `/admin/events/{event_slug}/email-deliveries` | `email_delivery.view` | `admin` |
| `POST` | `/admin/events/{event_slug}/email-deliveries/{delivery_id}/retry` | `email_delivery.manage` | `admin` |

Role summary:

| Role | Phase 7 access |
|---|---|
| `admin` | All endpoints above; event create/list require an admin membership on at least one event |
| `viewer` | Attendee list/detail (restricted schema) and all four analytics endpoints; email search is denied |
| `checkin` | No Phase 7 admin endpoints; use `/events/{event_slug}/checkins/*` instead |

Unknown event slugs, wrong-event memberships, and insufficient roles all return
the standard `403 FORBIDDEN` envelope without revealing whether another event
exists. Cross-event attendee, registration, ticket, staff, audit, and delivery
references return `404 NOT_FOUND`.

### Common request conventions

- Collections return `{"items": [...], "page": 1, "page_size": 50, "total": 12}`.
- `page >= 1`; `1 <= page_size <= 100`; default `page_size` is `50`.
- Sorting is stable: the listed sort key is followed by a UUID/ID tiebreaker.
- Date/time query parameters must be timezone-aware ISO 8601 values.
- Public references are `urn` for attendees and registrations, `ticket_code` for
  tickets, UUID for staff users, audit entries, and email deliveries.
- No response includes raw ticket tokens, token hashes, provider secrets, SQL
  errors, or internal numeric IDs.

### Event contracts

`POST /admin/events` creates a `draft` event and assigns the caller as its first
admin. `slug` is lowercase alphanumeric with single hyphens; `timezone` must be a
valid IANA name; all timestamps must include an offset. Timeline rules are:
`ends_at > starts_at`, `registration_opens_at < starts_at`,
`registration_closes_at <= starts_at`, and
`registration_closes_at > registration_opens_at`.

```bash
export ADMIN_JWT='replace-with-a-supabase-jwt-for-an-admin-user'
export BASE='http://127.0.0.1:8000/api/v1/admin'

curl -X POST "$BASE/events" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H 'Content-Type: application/json' \
  -d '{
    "slug": "summer-social-2026",
    "name": "Summer Social",
    "starts_at": "2026-07-01T09:00:00Z",
    "ends_at": "2026-07-01T18:00:00Z",
    "timezone": "UTC",
    "venue": "Main Hall",
    "capacity": 200,
    "registration_opens_at": "2026-06-01T00:00:00Z",
    "registration_closes_at": "2026-06-30T23:59:00Z"
  }'
```

`PATCH /admin/events/{slug}` accepts only mutable fields; `slug` and `status` are
immutable and invalid timeline combinations return `422 VALIDATION_ERROR`. The
only lifecycle transitions are `draft -> published -> archived`; revisiting an
archived event returns `409 CONFLICT`. Event mutations write
`event.created`, `event.updated`, `event.published`, or `event.archived` audits.

```bash
curl -X POST "$BASE/events/summer-social-2026/publish" \
  -H "Authorization: Bearer $ADMIN_JWT"

curl "$BASE/events?status=published&page=1&page_size=20" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Attendee and registration contracts

Attendee listing supports `search` (name or URN), exact `urn`, admin-only exact
`email`, `registration_status`, `ticket_status`, `check_in_status`
(`pending`/`checked_in`), `sort_by` (`registered_at`/`name`), and `sort_order`
(`asc`/`desc`). Admins receive `AdminAttendeeResponse` with contact details,
registration/ticket/check-in state, station, and public references. Viewers
receive only `attendee_reference`, `full_name`, `urn`, `registration_status`,
`ticket_status`, `check_in_status`, and `checked_in_at`; an `email` filter from a
viewer returns `403`.

```bash
curl "$BASE/events/summer-social-2026/attendees?check_in_status=checked_in&sort_by=name&sort_order=asc" \
  -H "Authorization: Bearer $ADMIN_JWT"

curl "$BASE/events/summer-social-2026/attendees/URN-EXAMPLE" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

Registration listing supports `reference` (URN), `name`, `email`,
`registration_status`, `ticket_status`, and `check_in_status`. Cancellation is
transactional and idempotent:

- `registered` -> `cancelled`; an `active` ticket is revoked in the same commit.
- Repeated cancellation is a no-op and creates no second audit record.
- `checked_in`, a used ticket, or an existing check-in record returns `409` and
  preserves attendance history.
- A `registration.cancelled` audit records safe status fields and whether a
  ticket was revoked.

```bash
curl -X POST "$BASE/events/summer-social-2026/registrations/URN-EXAMPLE/cancel" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Ticket contracts and resend behavior

Ticket listing supports `ticket_status` and partial `reference` (`ticket_code`)
filters. Responses contain only public references and statuses; tokens and
hashes are never returned. Revocation changes `active` to `revoked` in one
transaction with a `ticket.revoked` audit. Repeated revocation is idempotent;
`used`, `expired`, and already checked-in tickets return `409`.

Resend never calls Resend directly and never regenerates a credential. It creates
a new `pending` `email_deliveries` job with `purpose=ticket_issued` and the next
`resend_sequence` for the worker. A `pending` or `failed` job for the same ticket
blocks a duplicate resend with `409 RESEND_ALREADY_PENDING`. Cancelled
registrations and non-active tickets cannot be resent.

```bash
curl -X POST "$BASE/events/summer-social-2026/tickets/TICKET-CODE-EXAMPLE/resend" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Staff contracts

`POST /admin/events/{slug}/staff` takes `{"user_id": "<supabase-auth-uuid>",
"role": "admin|checkin|viewer"}`. Invalid UUIDs return `422`. Duplicate
memberships return `409`. Role changes write `staff.role_changed` audits,
addition writes `staff.added`, and removal writes `staff.removed`. The final
`admin` for an event cannot be demoted or removed (`409 FINAL_ADMIN`).

```bash
curl -X POST "$BASE/events/summer-social-2026/staff" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"00000000-0000-0000-0000-000000000001","role":"viewer"}'

curl -X PATCH "$BASE/events/summer-social-2026/staff/00000000-0000-0000-0000-000000000001" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"role":"checkin"}'
```

### Analytics metrics and filters

All analytics endpoints accept `admin` and `viewer`. `from_date` and `to_date`
are optional, timezone-aware, `to_date >= from_date`, and at most 10 years apart.
When both are supplied, granularity is `day` for ranges up to 31 days, `week` up
to 180 days, and `month` otherwise; without a complete range it is `month`.
Buckets are `date_trunc` of `registered_at` or `checked_in_at` on PostgreSQL.

| Metric | Definition |
|---|---|
| `total_registrations` | All registrations for the event |
| `cancelled_registrations` | Registrations with status `cancelled` |
| `confirmed_registrations` | `total_registrations - cancelled_registrations` |
| `checked_in_attendees` | Registrations with status `checked_in` |
| `not_checked_in_attendees` | `max(confirmed_registrations - checked_in_attendees, 0)` |
| `declined_rsvps` | Distinct webhook submission IDs with outcome `ignored_declined` for the event slug |
| `active_tickets` / `used_tickets` / `revoked_tickets` / `expired_tickets` | Ticket status counts joined through the event's registrations |
| `pending_email_deliveries` / `sent_email_deliveries` / `failed_email_deliveries` / `dead_letter_email_deliveries` | Delivery status counts joined through the event's registrations |
| `attendance_percentage` | `round(checked_in_attendees / confirmed_registrations * 100, 2)`, or `0.0` when there are no confirmed registrations |
| `total_in_range` | Sum of registration bucket counts in the requested range |
| `attempt_summary.total_attempts` | Sum of `email_deliveries.attempts` for the event |
| `attempt_summary.max_attempts` | Maximum attempt count, or `0` for an empty outbox |
| `attempt_summary.average_attempts` | Mean attempt count rounded to two decimals, or `0.0` |
| `attempt_summary.retried_deliveries` | Number of delivery rows with `attempts > 1` |

Analytics responses contain aggregate numbers only: no names, emails, URNs,
tokens, or ticket references.

```bash
curl "$BASE/events/summer-social-2026/analytics/attendance" \
  -H "Authorization: Bearer $ADMIN_JWT"

curl "$BASE/events/summer-social-2026/analytics/registrations?from_date=2026-06-01T00:00:00Z&to_date=2026-07-02T00:00:00Z" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Export contracts

Four admin-only endpoints stream `attendees` or `checkins` as CSV or XLSX:
`/exports/attendees.csv`, `/exports/attendees.xlsx`,
`/exports/checkins.csv`, and `/exports/checkins.xlsx`. Responses use
`Content-Disposition: attachment; filename="<kind>-<event-slug>.<ext>"`.
SQL uses server-side batching (`yield_per(500)`) and CSV/XLSX generation is
streaming or write-only, so memory stays bounded. Each request writes an
`export.attendees` or `export.checkins` audit containing only the format; no
exported content is logged. Exports share the `admin_export` rate-limit scope
(default `EVENT_ADMIN_EXPORT_RATE_LIMIT=10` per window).

| Export | Columns |
|---|---|
| Attendees | `name`, `urn`, `email`, `phone`, `registration_status`, `ticket_status`, `registered_at`, `checked_in_at`, `station` |
| Check-ins | `name`, `urn`, `email`, `phone`, `registration_status`, `ticket_status`, `checked_in_at`, `station`, `source` |

Datetimes are ISO 8601 UTC strings. Any cell beginning with `=`, `+`, `-`, or `@`
is prefixed with a single quote to prevent spreadsheet formula injection. Ticket
codes, raw tokens, token hashes, and website/API secrets are not exported.

```bash
curl "$BASE/events/summer-social-2026/exports/attendees.csv" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -o attendees.csv
```

### Audit logs

`GET /admin/events/{slug}/audit-logs` supports `action`, `actor_user_id`,
`from_date`, `to_date`, `page`, `page_size`, and `sort_order`. Results are ordered
by `created_at` with an ID tiebreaker. Responses include
`audit_reference`, `action`, `target_type`, `target_id`, `redacted context`,
`actor_user_id`, and `created_at`. Context is allow-listed to operation metadata;
tokens, hashes, emails, phones, names, URNs, and passwords are removed. There are
no audit mutation endpoints: `PATCH`/`DELETE` return `405`.

Audited Phase 7 actions include `event.created`, `event.updated`,
`event.published`, `event.archived`, `registration.cancelled`,
`ticket.revoked`, `ticket.resend_queued`, `staff.added`,
`staff.role_changed`, `staff.removed`, `export.attendees`,
`export.checkins`, and `email_retry.queued`.

```bash
curl "$BASE/events/summer-social-2026/audit-logs?action=ticket.revoked&sort_order=desc" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Email delivery monitoring and retry

`GET /admin/events/{slug}/email-deliveries` supports `status`,
`registration_reference`, `ticket_reference`, `min_attempts`, `max_attempts`,
`error_code`, `next_attempt_before`, and `next_attempt_after`. Responses expose
the delivery UUID, public references, purpose, status, attempts, resend sequence,
error code, retry timestamp, creation time, and sent time. They never contain
recipient addresses, token values, token hashes, or provider bodies.

`POST /admin/events/{slug}/email-deliveries/{delivery_id}/retry` accepts only
`failed` or `dead_letter` jobs. It preserves the original record: a `failed` job
is moved to `dead_letter` with its attempt count and error code intact, and a new
`pending` job with the next `resend_sequence` is queued. A terminal dead-letter
cannot be retried again, and another pending/failed job for the same ticket
returns `409 RESEND_ALREADY_PENDING`. No Resend call is made from the API.

```bash
curl "$BASE/events/summer-social-2026/email-deliveries?status=failed&min_attempts=1" \
  -H "Authorization: Bearer $ADMIN_JWT"

curl -X POST "$BASE/events/summer-social-2026/email-deliveries/00000000-0000-0000-0000-000000000009/retry" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Phase 7 setup, migrations, and tests

```bash
python -m pip install -e ".[dev]"   # includes openpyxl>=3.1,<4.0
alembic upgrade head
alembic check
alembic current

# Optional: inspect the Phase 7 revision in isolation
alembic downgrade 20261127_0002
alembic upgrade head
```

Run the full PostgreSQL suite sequentially; these fixtures share one test
database and truncate domain tables between tests:

```bash
export EVENT_APP_ENV=test
export EVENT_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55432/event_test'
export EVENT_TEST_POSTGRES_URL="$EVENT_DATABASE_URL"
python -m pytest -q
```

## Monorepo layout (Phase 8 setup)

The existing Git repository now contains both applications; there is no separate
frontend repository and no nested Git repository under `frontend/`.

```text
Event_backend/
├── app/                 # FastAPI application
├── alembic/             # Backend migrations
├── tests/               # Backend tests
├── pyproject.toml
├── alembic.ini
├── README.md
├── frontend/            # Next.js application
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── next.config.ts
│   └── .env.example
├── .gitignore
└── .env.example
```

Backend files stay at the repository root. The frontend is independently
buildable from `frontend/`; copy `frontend/.env.example` to
`frontend/.env.local` and fill in real values locally. Do not commit `.env.local`.

```bash
cd frontend
npm install
npm run dev
npm run build
```

### Deployment configuration

No deployment is performed by this setup step. When Phase 8 is ready to deploy:

| Platform / service | Root Directory | Notes |
|---|---|---|
| Vercel (Next.js frontend) | `frontend/` | Build command `npm run build`; install from `frontend/package-lock.json` |
| Render (FastAPI API) | `.` | Uses root `pyproject.toml`, `app/`, and `alembic/` |
| Render (email worker) | `.` | Uses the same root working directory and environment as the API |

Because both Render services use the repository root, backend commands and
Alembic migrations must be run from `.`, while Vercel build commands must be run
from `frontend/`.

## Local setup

Requires Python 3.12 or 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and set a real database URL. Never commit `.env`.

Start the server:

```bash
uvicorn app.main:app --reload
```

Then visit:

- Health: <http://127.0.0.1:8000/health>
- API health: <http://127.0.0.1:8000/api/v1/health>
- Readiness: <http://127.0.0.1:8000/api/v1/ready>
- OpenAPI docs: <http://127.0.0.1:8000/docs>

## Environment variables

All variables use the `EVENT_` prefix and are validated at startup.

| Variable | Required | Default | Notes |
|---|---:|---|---|
| `EVENT_APP_ENV` | Yes | — | `local`, `test`, `development`, `staging`, or `production` |
| `EVENT_DATABASE_URL` | Yes | — | `postgresql+psycopg://...` or `sqlite+pysqlite://...` |
| `EVENT_SERVICE_NAME` | No | `event-management-api` | Reported by health endpoints |
| `EVENT_APP_VERSION` | No | `0.1.0` | Reported by API health |
| `EVENT_API_VERSION` | No | `v1` | Controls `/api/v1` prefix |
| `EVENT_DOCS_ENABLED` | No | `true` | Set `false` in production if desired |
| `EVENT_LOG_LEVEL` | No | `INFO` | Standard Python log level |
| `EVENT_LOG_FORMAT` | No | `json` | `json` or `console` |
| `EVENT_CORS_ORIGINS` | No | empty | Comma-separated allowed origins |
| `EVENT_DB_POOL_SIZE` | No | `5` | PostgreSQL pool size |
| `EVENT_DB_MAX_OVERFLOW` | No | `10` | PostgreSQL overflow |
| `EVENT_DB_POOL_TIMEOUT_SECONDS` | No | `30` | Pool checkout timeout |
| `EVENT_DB_POOL_RECYCLE_SECONDS` | No | `1800` | Connection recycle age |
| `EVENT_DB_STATEMENT_TIMEOUT_MS` | No | `30000` | Per-statement timeout |
| `EVENT_DB_PREPARE_THRESHOLD` | No | `0` | psycopg v3 prepared statements; `0` for transaction pooling |
| `EVENT_DB_ECHO` | No | `false` | SQL echo; never enable in production |
| `EVENT_WEBHOOK_SIGNING_KEYS` | No | empty | JSON object of key ID → shared secret (`SecretStr`) |
| `EVENT_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` | No | `300` | Accepted clock skew for webhook timestamps |
| `EVENT_SUPABASE_URL` | No | — | Supabase project URL; supplies default issuer/JWKS URL |
| `EVENT_SUPABASE_JWT_STRATEGY` | No | `hs256` | `hs256` shared secret or `jwks` asymmetric keys |
| `EVENT_SUPABASE_JWT_SECRET` | No | — | HS256 signing secret (`SecretStr`) |
| `EVENT_SUPABASE_JWKS_URL` | No | — | Explicit JWKS URL; overrides the Supabase default |
| `EVENT_JWT_ISSUER` | No | derived | Explicit issuer; overrides the Supabase default |
| `EVENT_JWT_AUDIENCE` | No | `authenticated` | Expected JWT audience |
| `EVENT_JWT_LEEWAY_SECONDS` | No | `0` | Small clock skew allowance for `exp`/`iat` |
| `EVENT_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Fixed-window duration |
| `EVENT_WEBHOOK_RATE_LIMIT` | No | `60` | Requests per webhook scope window |
| `EVENT_CHECKIN_VERIFY_RATE_LIMIT` | No | `120` | Requests per check-in verification window |
| `EVENT_CHECKIN_CONFIRM_RATE_LIMIT` | No | `60` | Requests per check-in confirmation window |
| `EVENT_ADMIN_EXPORT_RATE_LIMIT` | No | `10` | Requests per administrative export window |
| `EVENT_TICKET_TOKEN_DERIVATION_KEY` | No | local-only default | `SecretStr`; required override in production |
| `EVENT_RESEND_API_KEY` | Worker only | — | Resend API key (`SecretStr`) |
| `EVENT_RESEND_FROM_EMAIL` | Worker only | — | Verified sender address |
| `EVENT_RESEND_FROM_NAME` | No | `Event Management` | Sender display name |
| `EVENT_EMAIL_WORKER_POLL_INTERVAL_SECONDS` | No | `5` | Idle polling interval |
| `EVENT_EMAIL_WORKER_BATCH_SIZE` | No | `10` | Jobs claimed per pass |
| `EVENT_EMAIL_WORKER_MAX_ATTEMPTS` | No | `5` | Attempts before dead-letter |
| `EVENT_EMAIL_WORKER_LEASE_SECONDS` | No | `60` | Interrupted-job visibility timeout |
| `EVENT_EMAIL_RETRY_BACKOFF_INITIAL_SECONDS` | No | `30` | First retry delay |
| `EVENT_EMAIL_RETRY_BACKOFF_MULTIPLIER` | No | `2` | Exponential multiplier |
| `EVENT_EMAIL_RETRY_BACKOFF_MAX_SECONDS` | No | `3600` | Backoff cap |

Sensitive values are parsed as Pydantic `SecretStr` and are never rendered in logs
or error responses. Redis is not used; rate-limit counters are stored in PostgreSQL.

## Security architecture

- **Webhooks:** `require_webhook_auth` reads the raw body, resolves the signing
  secret by `X-Webhook-Key-Id`, validates `X-Webhook-Timestamp` within the configured
  tolerance, and verifies `HMAC-SHA256(timestamp.POST./api/v1/webhooks/google-forms.raw_body)`
  using `hmac.compare_digest`. Missing, invalid, expired, or unknown-key requests
  receive HTTP 401. Add a new key ID to rotate secrets; remove the old one only
  after all senders have switched.
- **JWTs:** `get_current_user` accepts only `Bearer` tokens and delegates to
  `JwtVerifier`, which verifies the signature before reading claims, checks issuer,
  audience, expiration, and required claims, and requires a UUID `sub`. The `jwks`
  strategy uses `PyJWKClient` with key caching and refreshes on unknown `kid`, so
  Supabase key rotation is handled without redeployment.
- **RBAC:** `require_permission(Permission.X)` reads `event_id` from the route,
  loads the authenticated user's `staff_memberships` row for that event, and checks
  the role mapping. JWT role claims are never trusted. Unknown permissions and
  missing/wrong-event memberships deny access (HTTP 403).
- **Ticket tokens:** raw QR credentials are derived in memory from a random public
  reference and a server-side `SecretStr`; only their deterministic SHA-256 digests
  are persisted. The standalone generator `generate_ticket_token()` remains available
  for future flows that can hand the raw value directly to a verifier.
- **Rate limiting:** a shared `rate_limit_counters` table and atomic upsert provide
  fixed-window limits across backend instances. Subjects must be opaque; callers
  should hash IPs or other personal identifiers before passing them.

No secrets, signatures, raw bodies, or raw tokens are logged. Field-level privacy
for attendee responses is enforced by the explicit admin/viewer schemas added in
Phase 7; ORM objects are never serialized directly.

## Database / Alembic

All mapped classes are registered through `app.db.models`; the shared rate-limit
table is registered through `app.security.rate_limit`. Alembic reads the same
`EVENT_DATABASE_URL` setting as the application.

```bash
# Apply all revisions
alembic upgrade head

# Verify the database matches the model metadata
alembic check

# Destructive: drops all domain tables, enums, and rate-limit counters
alembic downgrade base
```

Revision `20261127_0001` creates all nine domain tables, their native enums,
foreign keys, unique constraints, and indexes. Revision `20261127_0002` adds the
`rate_limit_counters` table. Revision `20261127_0003` adds the email resend
sequence, sequence-scoped uniqueness, and the webhook analytics index. Only
hashed ticket tokens and webhook payload hashes are stored; raw ticket tokens and
raw webhook payloads are never persisted. Phases 5 and 6 reused the existing
tables and constraints without adding revisions.

## Tests and quality checks

```bash
# Portable tests (no PostgreSQL required)
pytest -q -m 'not postgres'

# Full suite, including PostgreSQL-specific schema and migration tests
export EVENT_APP_ENV=test
export EVENT_DATABASE_URL='postgresql+psycopg://.../event_test'
export EVENT_TEST_POSTGRES_URL="$EVENT_DATABASE_URL"
pytest -q

ruff check .
ruff format --check .
mypy app
```

PostgreSQL tests require an isolated database whose URL contains `test`.
`EVENT_TEST_POSTGRES_URL` must equal `EVENT_DATABASE_URL` so Alembic verifies the
same database. The fixtures reset the `public` schema before applying migrations;
never point these variables at production or staging.

CI runs the portable checks on Python 3.12.

## Response formats

Success:

```json
{
  "status": "healthy",
  "service": "event-management-api"
}
```

Errors:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The requested resource was not found."
  }
}
```

All responses include `X-Correlation-ID`, which is also attached to structured log
events.
