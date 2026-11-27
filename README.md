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

Not implemented yet: scanner APIs, admin workflows, and login endpoints. Ticket
issuance and email delivery were added in Phase 5; the registration webhook was
added in Phase 4; JWT verification primitives were added in Phase 3; database
models were added in Phase 2.

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

Not implemented yet: check-in API and admin APIs. QR generation, email sending,
and the worker were added in Phase 5; the HMAC-authenticated registration webhook
was added in Phase 4; security primitives were added in Phase 3.

## Phase 3 scope

Implemented as reusable primitives only (no product endpoints):

- HMAC-SHA256 webhook authentication with key-ID rotation and timestamp tolerance
- Supabase JWT verification with HS256 shared secret or rotating JWKS keys
- Event-scoped RBAC backed by `staff_memberships`, exposed as FastAPI dependencies
- Secure ticket-token generation, SHA-256 hashing, and constant-time comparison
- Shared PostgreSQL fixed-window rate limiting for webhook, check-in, and export scopes

Not implemented yet: login endpoints, scanner API, and admin API endpoints. QR
generation, Resend integration, and the email worker were added in Phase 5.

## Phase 4 scope

Implemented:

- `POST /api/v1/webhooks/google-forms` using the Phase 3 HMAC dependency and shared webhook rate limiter
- Pydantic RSVP request contract with explicit attendance values and safe normalization
- Transactional service layer for event resolution, availability, capacity, attendee identity, and registration
- Idempotent processing backed by the existing `webhook_events` ledger and database constraints
- Controlled outcomes for registered, declined, duplicate, already registered, validation rejection, event unavailable, capacity reached, and identity conflict

Ticket generation, QR codes, and email delivery were added in Phase 5. Still not
implemented: scanner endpoints, admin endpoints, and automatic event creation.

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

Not implemented yet: scanner endpoints, frontend scanner, admin dashboard, deployment,
and any Phase 6 functionality. No migration was required for Phase 5: the existing
`tickets`, `email_deliveries`, and webhook-ledger constraints cover the workflow.

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
for attendee responses must still be enforced by future response schemas.

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
`rate_limit_counters` table. Only hashed ticket tokens and webhook payload hashes
are stored; raw ticket tokens and raw webhook payloads are never persisted.
Phase 5 reused these tables and constraints without adding a revision.

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
