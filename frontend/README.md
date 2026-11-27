# Event Management Frontend

Next.js 16 App Router frontend for the Event Management backend. This package contains the Phase 8.1 foundation: design system, Supabase SSR authentication, protected routing, typed API client, and application shell.

## Requirements

- Node.js 22+ (Node 26 is used in local verification)
- npm
- A Supabase project using the same JWT issuer/audience configuration as the backend
- A running FastAPI backend for authenticated API calls

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The application is served at `http://localhost:3000`.

### Environment variables

`.env.local` uses public values only:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-publishable-key
```

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | FastAPI base URL including `/api/v1` |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key |

Never put a service-role key, JWT secret, database URL, webhook key, or any other backend secret in `NEXT_PUBLIC_*` variables. Backend authorization always remains authoritative.

For browser CORS to work, add the frontend origin to the backend `EVENT_CORS_ORIGINS` allow-list.

## Scripts

```bash
npm run dev        # development server
npm run build      # production build
npm run start      # production server
npm run lint       # ESLint
npm run typecheck  # TypeScript strict check
npm test           # Vitest unit tests
npm run test:watch # Vitest watch mode
```

## Architecture

### Supabase SSR

- `src/lib/supabase/client.ts` creates a singleton browser client with `@supabase/ssr`.
- `src/lib/supabase/server.ts` creates a request-scoped server client using async `cookies()`.
- `src/proxy.ts` refreshes the session on navigation and writes refreshed cookies to the response. Next.js 16 uses `proxy.ts` in place of `middleware.ts`.
- `src/app/auth/logout/route.ts` signs out through the server client.
- `src/components/providers/auth-provider.tsx` exposes the authenticated user, refresh, and sign-out actions.
- `/login` uses email/password Supabase Auth. Session expiry returns the user to `/login?reason=session_expired`.
- Protected dashboard routes verify the user server-side in `src/app/(dashboard)/layout.tsx` and redirect unauthenticated users to `/login`.

Authentication against a real Supabase project has not been performed as part of this stage. Local configuration and real-project verification are still required.

### API client

- `src/lib/api/client.ts` reads `NEXT_PUBLIC_API_BASE_URL`, attaches the current Supabase access token, supports query/pagination params, JSON requests, and binary downloads.
- `src/lib/api/errors.ts` parses the backend envelope `{ error: { code, message, details? } }` and exposes 401/403/422/429 helpers plus `retry_after_seconds`.
- `src/lib/api/query-client.ts` enables retries only for idempotent query failures and sends all 401 responses to the session-expiry handler. Mutations never auto-retry.
- Access tokens are never written to localStorage or logged.

See [`docs/API_CONTRACT.md`](./docs/API_CONTRACT.md) for the verified backend contract.

### Permission-aware navigation

The event list endpoint requires global `event.manage`, so a successful `GET /api/v1/admin/events` is used to decide whether to show event-management navigation. Roles are never inferred from JWT claims. Permissions that cannot be verified from an existing endpoint remain hidden by default. The backend validates every request against `staff_memberships`.

### Event selection

The selected event slug is kept in the `?event=` query parameter. No token or session data is persisted in browser storage.

## Design system

Reusable components live in `src/components/ui`:

- `Button`, `Card`, `Badge`
- `Dialog`, `DropdownMenu`
- `Input`, `Label`, `Select`, `Textarea`, `FormField`
- `Alert`, `EmptyState`, `ErrorState`, `Skeleton`
- Sonner-based `Toaster`

Design tokens are defined in `src/app/globals.css` with Tailwind CSS 4 `@theme`. The visual direction is restrained and neutral with a single primary accent.

## Scope

Implemented in Phase 8.1:

- `/login`
- `/dashboard`
- `/events`
- Protected shell with responsive sidebar, top navigation, profile menu, and logout
- Event selection and empty states using the real event listing endpoint

Not implemented yet: event creation, analytics, attendee management, scanner flows, and deployment.
