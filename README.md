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
scanner APIs, admin workflows, and Supabase JWT authentication. Database models
were added in Phase 2.

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

Not implemented yet: registration webhook endpoints, HMAC authentication, QR
generation, email sending/worker, check-in API, admin APIs, and Supabase JWT auth.

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

## Database / Alembic

All mapped classes are registered through `app.db.models`. Alembic reads the same
`EVENT_DATABASE_URL` setting as the application.

```bash
# Apply the initial schema
alembic upgrade head

# Verify the database matches the model metadata
alembic check

# Initial revision only: drops all domain tables and native enum types
alembic downgrade base
```

Revision `20261127_0001` creates all nine domain tables, their native enums,
foreign keys, unique constraints, and indexes. Only hashed ticket tokens and
webhook payload hashes are stored; raw ticket tokens and raw webhook payloads are
never persisted.

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
