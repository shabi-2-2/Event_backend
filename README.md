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

Not implemented yet: registration webhooks, ticket generation, email delivery,
scanner APIs, admin workflows, and login endpoints. JWT verification primitives
were added in Phase 3; database models were added in Phase 2.

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

Not implemented yet: registration webhook endpoints, HMAC-authenticated routes,
QR generation, email sending/worker, check-in API, and admin APIs. Security
primitives were added in Phase 3.

## Phase 3 scope

Implemented as reusable primitives only (no product endpoints):

- HMAC-SHA256 webhook authentication with key-ID rotation and timestamp tolerance
- Supabase JWT verification with HS256 shared secret or rotating JWKS keys
- Event-scoped RBAC backed by `staff_memberships`, exposed as FastAPI dependencies
- Secure ticket-token generation, SHA-256 hashing, and constant-time comparison
- Shared PostgreSQL fixed-window rate limiting for webhook, check-in, and export scopes

Not implemented yet: Google Forms webhook endpoint, login endpoints, QR generation,
Resend integration, email worker, scanner API, and admin API endpoints.

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
- **Ticket tokens:** raw values are generated with `secrets.token_urlsafe(32)`;
  only their deterministic SHA-256 digests are suitable for persistence.
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
