import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AnalyticsDateRangeParams,
  AttendanceAnalyticsResponse,
  EmailAnalyticsResponse,
  EventRecord,
  OverviewAnalyticsResponse,
  RegistrationAnalyticsResponse,
} from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { createAppQueryClient } from "@/lib/api/query-client";

const navigation = vi.hoisted(() => {
  let searchParams = new URLSearchParams();

  return {
    replace: vi.fn((url: string) => {
      const queryIndex = url.indexOf("?");
      searchParams = new URLSearchParams(
        queryIndex >= 0 ? url.slice(queryIndex + 1) : "",
      );
    }),
    setSearch: (query = "") => {
      searchParams = new URLSearchParams(query);
    },
    useSearchParams: () => searchParams,
  };
});

const api = vi.hoisted(() => ({
  events: {
    list: vi.fn(),
    get: vi.fn(),
  },
  analytics: {
    overview: vi.fn(),
    registrations: vi.fn(),
    attendance: vi.fn(),
    emailDeliveries: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  usePathname: () => "/dashboard",
  useSearchParams: () => navigation.useSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("recharts", async () => await import("@/test/mocks/recharts"));

import { EventSelectionProvider } from "@/components/layout/event-selection-context";
import DashboardPage from "@/app/(dashboard)/dashboard/page";

const eventA: EventRecord = {
  slug: "event-a",
  name: "Alpha Summit",
  description: null,
  starts_at: "2026-06-20T09:00:00.000Z",
  ends_at: "2026-06-20T17:00:00.000Z",
  timezone: "UTC",
  venue: "Hall A",
  capacity: 100,
  registration_opens_at: "2026-01-01T00:00:00.000Z",
  registration_closes_at: "2027-06-19T00:00:00.000Z",
  status: "published",
  created_at: "2026-05-01T00:00:00.000Z",
  updated_at: "2026-05-01T00:00:00.000Z",
};

const eventB: EventRecord = {
  ...eventA,
  slug: "event-b",
  name: "Beta Forum",
  venue: "Hall B",
};

const overviewA: OverviewAnalyticsResponse = {
  total_registrations: 10,
  confirmed_registrations: 8,
  cancelled_registrations: 2,
  declined_rsvps: 1,
  checked_in_attendees: 3,
  not_checked_in_attendees: 5,
  active_tickets: 4,
  used_tickets: 3,
  revoked_tickets: 1,
  expired_tickets: 0,
  pending_email_deliveries: 2,
  sent_email_deliveries: 6,
  failed_email_deliveries: 1,
  dead_letter_email_deliveries: 0,
};

const overviewB: OverviewAnalyticsResponse = {
  ...overviewA,
  total_registrations: 5,
  confirmed_registrations: 5,
  cancelled_registrations: 0,
  checked_in_attendees: 1,
  not_checked_in_attendees: 4,
};

const registrationA: RegistrationAnalyticsResponse = {
  granularity: "day",
  from_date: null,
  to_date: null,
  buckets: [{ period_start: "2026-06-20T09:00:00.000Z", period: "day", count: 7 }],
  total_in_range: 7,
};

const registrationB: RegistrationAnalyticsResponse = {
  ...registrationA,
  buckets: [{ period_start: "2026-06-20T09:00:00.000Z", period: "day", count: 2 }],
  total_in_range: 2,
};

const attendanceA: AttendanceAnalyticsResponse = {
  confirmed_registrations: 8,
  checked_in_attendees: 3,
  not_checked_in_attendees: 5,
  attendance_percentage: 37.5,
  buckets: [{ period_start: "2026-06-20T09:00:00.000Z", period: "day", count: 3 }],
};

const attendanceB: AttendanceAnalyticsResponse = {
  confirmed_registrations: 5,
  checked_in_attendees: 1,
  not_checked_in_attendees: 4,
  attendance_percentage: 20,
  buckets: [{ period_start: "2026-06-20T09:00:00.000Z", period: "day", count: 1 }],
};

const emailA: EmailAnalyticsResponse = {
  total_deliveries: 9,
  status_counts: { pending: 2, sent: 6, failed: 1, dead_letter: 0 },
  attempt_summary: {
    total_attempts: 12,
    max_attempts: 3,
    average_attempts: 1.33,
    retried_deliveries: 2,
  },
};

const eventsBySlug: Record<string, EventRecord> = {
  [eventA.slug]: eventA,
  [eventB.slug]: eventB,
};

function eventPage(items: EventRecord[]) {
  return { items, page: 1, page_size: 100, total: items.length };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

function dashboardTree(queryClient: ReturnType<typeof createAppQueryClient>) {
  return (
    <QueryClientProvider client={queryClient}>
      <EventSelectionProvider>
        <DashboardPage />
      </EventSelectionProvider>
    </QueryClientProvider>
  );
}

function renderDashboard(query = "") {
  navigation.setSearch(query);
  const queryClient = createAppQueryClient();
  const view = render(dashboardTree(queryClient));

  return { ...view, queryClient };
}

describe("dashboard page integration", () => {
  beforeEach(() => {
    navigation.setSearch("");
    navigation.replace.mockClear();

    api.events.list.mockReset();
    api.events.get.mockReset();
    api.analytics.overview.mockReset();
    api.analytics.registrations.mockReset();
    api.analytics.attendance.mockReset();
    api.analytics.emailDeliveries.mockReset();

    api.events.list.mockImplementation(async () => eventPage([eventA, eventB]));
    api.events.get.mockImplementation(async (slug: string) => eventsBySlug[slug]);
    api.analytics.overview.mockImplementation(
      async (slug: string) => (slug === eventB.slug ? overviewB : overviewA),
    );
    api.analytics.registrations.mockImplementation(
      async (slug: string, range: AnalyticsDateRangeParams = {}) =>
        range.from_date
          ? {
              ...registrationB,
              from_date: range.from_date,
              to_date: range.to_date ?? null,
            }
          : slug === eventB.slug
            ? registrationB
            : registrationA,
    );
    api.analytics.attendance.mockImplementation(
      async (slug: string, range: AnalyticsDateRangeParams = {}) =>
        range.from_date ? attendanceB : slug === eventB.slug ? attendanceB : attendanceA,
    );
    api.analytics.emailDeliveries.mockImplementation(async () => emailA);
  });

  it("loads backend event and analytics data for the selected event", async () => {
    renderDashboard("?event=event-a");

    expect(await screen.findByRole("heading", { name: "Alpha Summit" })).toBeInTheDocument();
    expect(await screen.findByText("7 registrations in range")).toBeInTheDocument();
    expect(screen.getByText("Hall A")).toBeInTheDocument();
    expect(screen.getByText("37.5%")).toBeInTheDocument();
    expect(screen.getByText("Registration: Open")).toBeInTheDocument();

    expect(api.events.list).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 100 }),
      expect.any(AbortSignal),
    );
    expect(api.events.get).toHaveBeenCalledWith("event-a", expect.any(AbortSignal));
    expect(api.analytics.overview).toHaveBeenCalledWith("event-a", expect.any(AbortSignal));
    expect(api.analytics.emailDeliveries).toHaveBeenCalledWith(
      "event-a",
      expect.any(AbortSignal),
    );
    expect(api.analytics.registrations).toHaveBeenCalledWith(
      "event-a",
      expect.objectContaining({ from_date: undefined, to_date: undefined }),
      expect.any(AbortSignal),
    );
    expect(api.analytics.attendance).toHaveBeenCalledWith(
      "event-a",
      expect.objectContaining({ from_date: undefined, to_date: undefined }),
      expect.any(AbortSignal),
    );
  });

  it("requires explicit event selection and does not select an event automatically", async () => {
    renderDashboard();

    expect(await screen.findByText("Select an event")).toBeInTheDocument();
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(api.analytics.overview).not.toHaveBeenCalled();
    expect(api.analytics.registrations).not.toHaveBeenCalled();
  });

  it("shows a useful empty state when no events are available", async () => {
    api.events.list.mockResolvedValueOnce(eventPage([]));

    renderDashboard();

    expect(await screen.findByText("No events available")).toBeInTheDocument();
    expect(api.analytics.overview).not.toHaveBeenCalled();
  });

  it("renders empty analytics safely", async () => {
    const emptyOverview = Object.fromEntries(
      Object.keys(overviewA).map((key) => [key, 0]),
    ) as OverviewAnalyticsResponse;
    api.analytics.overview.mockResolvedValue(emptyOverview);
    api.analytics.registrations.mockResolvedValue({
      ...registrationA,
      buckets: [],
      total_in_range: 0,
    });
    api.analytics.attendance.mockResolvedValue({
      confirmed_registrations: 0,
      checked_in_attendees: 0,
      not_checked_in_attendees: 0,
      attendance_percentage: 0,
      buckets: [],
    });
    api.analytics.emailDeliveries.mockResolvedValue({
      total_deliveries: 0,
      status_counts: { pending: 0, sent: 0, failed: 0, dead_letter: 0 },
      attempt_summary: {
        total_attempts: 0,
        max_attempts: 0,
        average_attempts: 0,
        retried_deliveries: 0,
      },
    });

    renderDashboard("?event=event-a");

    expect(await screen.findByText("0 registrations in range")).toBeInTheDocument();
    expect(screen.getAllByText("No data to display")).toHaveLength(4);
  });

  it("renders unavailable metrics as an em dash when optional data is missing", async () => {
    api.analytics.overview.mockResolvedValue({
      total_registrations: 1,
    } as OverviewAnalyticsResponse);
    api.analytics.attendance.mockResolvedValue({
      attendance_percentage: 100,
    } as AttendanceAnalyticsResponse);

    renderDashboard("?event=event-a");

    expect(await screen.findByText("100%")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows clear forbidden and unauthorized states", async () => {
    api.analytics.overview.mockRejectedValueOnce(
      new ApiError(403, "FORBIDDEN", "You do not have access to this resource."),
    );
    const forbidden = renderDashboard("?event=event-a");

    expect(await screen.findByText("Access restricted")).toBeInTheDocument();
    expect(screen.getByText(/do not have analytics access/i)).toBeInTheDocument();
    forbidden.unmount();

    api.analytics.overview.mockRejectedValueOnce(
      new ApiError(401, "UNAUTHORIZED", "Authentication is required."),
    );
    renderDashboard("?event=event-a");

    expect(await screen.findByText("Authentication required")).toBeInTheDocument();
    expect(screen.getByText(/sign in again/i)).toBeInTheDocument();
  });

  it("does not retain analytics from a previous event while another event loads", async () => {
    const deferredOverview = createDeferred<OverviewAnalyticsResponse>();
    api.analytics.overview.mockImplementation(async (slug: string) =>
      slug === eventB.slug ? deferredOverview.promise : overviewA,
    );

    const view = renderDashboard("?event=event-a");
    expect(await screen.findByText("7 registrations in range")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Event"), {
      target: { value: eventB.slug },
    });
    expect(navigation.replace).toHaveBeenCalledWith("/dashboard?event=event-b", {
      scroll: false,
    });

    await act(async () => {
      view.rerender(dashboardTree(view.queryClient));
    });

    expect(screen.getByLabelText("Loading dashboard")).toBeInTheDocument();
    expect(screen.queryByText("7 registrations in range")).not.toBeInTheDocument();

    await act(async () => {
      deferredOverview.resolve(overviewB);
    });

    expect(await screen.findByRole("heading", { name: "Beta Forum" })).toBeInTheDocument();
    expect(await screen.findByText("2 registrations in range")).toBeInTheDocument();
    expect(api.analytics.overview).toHaveBeenCalledWith("event-a", expect.any(AbortSignal));
    expect(api.analytics.overview).toHaveBeenCalledWith("event-b", expect.any(AbortSignal));
  });

  it("refetches analytics for the selected range when the date filter changes", async () => {
    renderDashboard("?event=event-a");
    expect(await screen.findByText("7 registrations in range")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Analytics range"), {
      target: { value: "30d" },
    });

    expect(await screen.findByText("2 registrations in range")).toBeInTheDocument();

    const registrationCall = vi.mocked(api.analytics.registrations).mock.calls.at(-1);
    const attendanceCall = vi.mocked(api.analytics.attendance).mock.calls.at(-1);
    const range = registrationCall?.[1];

    expect(range?.from_date).toMatch(/^\d{4}-\d{2}-\d{2}T.*Z$/);
    expect(range?.to_date).toMatch(/^\d{4}-\d{2}-\d{2}T.*Z$/);
    expect(new Date(range?.to_date ?? "").getTime()).toBeGreaterThanOrEqual(
      new Date(range?.from_date ?? "").getTime(),
    );
    expect(attendanceCall?.[1]).toEqual(range);
    expect(api.analytics.registrations).toHaveBeenCalledTimes(2);
    expect(api.analytics.attendance).toHaveBeenCalledTimes(2);
  });

  it("invalidates all dashboard queries on refresh", async () => {
    renderDashboard("?event=event-a");
    expect(await screen.findByText("7 registrations in range")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /refresh dashboard data/i }));

    await waitFor(() => {
      expect(api.events.list).toHaveBeenCalledTimes(2);
      expect(api.events.get).toHaveBeenCalledTimes(2);
      expect(api.analytics.overview).toHaveBeenCalledTimes(2);
      expect(api.analytics.registrations).toHaveBeenCalledTimes(2);
      expect(api.analytics.attendance).toHaveBeenCalledTimes(2);
      expect(api.analytics.emailDeliveries).toHaveBeenCalledTimes(2);
    });
  });
});
