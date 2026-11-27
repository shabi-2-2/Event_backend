import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditLogRecord } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import {
  createNoRetryQueryClient,
  renderManagement,
} from "@/test/management-test-utils";

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  auditLogs: {
    list: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/audit-logs",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

import AuditLogsPage from "@/app/(dashboard)/events/[eventSlug]/audit-logs/page";

const firstEntry: AuditLogRecord = {
  audit_reference: "aud-1",
  action: "ticket.revoked",
  target_type: "ticket",
  target_id: "tkt-1",
  context: { from_status: "active", to_status: "revoked", sequence: 2 },
  actor_user_id: "11111111-1111-4111-8111-111111111111",
  created_at: "2026-06-01T10:00:00Z",
};

const secondEntry: AuditLogRecord = {
  audit_reference: "aud-2",
  action: "export.downloaded",
  target_type: "event",
  target_id: null,
  context: { format: "csv", outcome: "success" },
  actor_user_id: null,
  created_at: "2026-06-01T09:00:00Z",
};

function page(items: AuditLogRecord[], total = items.length, pageNumber = 1) {
  return { items, page: pageNumber, page_size: 25, total };
}

describe("audit log viewer", () => {
  beforeEach(() => {
    params.eventSlug = "summit-2026";
    api.auditLogs.list.mockReset().mockResolvedValue(page([firstEntry, secondEntry], 2));
  });

  it("lists event-scoped actor, action, target, timestamp, and redacted metadata", async () => {
    renderManagement(<AuditLogsPage />);

    expect(await screen.findByText("ticket.revoked")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Audit logs" });
    expect(within(table).getByText("ticket.revoked")).toBeInTheDocument();
    expect(within(table).getByText("11111111-1111-4111-8111-111111111111")).toBeInTheDocument();
    expect(within(table).getByText("tkt-1")).toBeInTheDocument();
    expect(within(table).getAllByText(/field\(s\)/)).toHaveLength(2);
    expect(api.auditLogs.list).toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 1, page_size: 25, sort_order: "desc" }),
      expect.any(AbortSignal),
    );
  });

  it("maps supported filters to backend query parameters", async () => {
    renderManagement(<AuditLogsPage />);
    await screen.findByText("ticket.revoked");

    fireEvent.change(screen.getByLabelText("Action"), {
      target: { value: "ticket.revoked" },
    });
    fireEvent.change(screen.getByLabelText("Actor user ID"), {
      target: { value: "11111111-1111-4111-8111-111111111111" },
    });
    fireEvent.change(screen.getByLabelText("Sort order"), { target: { value: "asc" } });
    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-06-01T08:30" },
    });
    fireEvent.change(screen.getByLabelText("To"), {
      target: { value: "2026-06-01T11:30" },
    });

    await waitFor(() => {
      expect(api.auditLogs.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({
          page: 1,
          action: "ticket.revoked",
          actor_user_id: "11111111-1111-4111-8111-111111111111",
          sort_order: "asc",
          from_date: "2026-06-01T08:30:00.000Z",
          to_date: "2026-06-01T11:30:00.000Z",
        }),
        expect.any(AbortSignal),
      );
    });
  });

  it("rejects invalid actor IDs before requesting a page", async () => {
    renderManagement(<AuditLogsPage />);
    await screen.findByText("ticket.revoked");

    fireEvent.change(screen.getByLabelText("Actor user ID"), {
      target: { value: "not-a-uuid" },
    });

    expect(screen.getByText("Actor ID must be a Supabase user UUID.")).toBeInTheDocument();
    expect(api.auditLogs.list).not.toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ actor_user_id: "not-a-uuid" }),
      expect.anything(),
    );
  });

  it("requests the next page when pagination is used", async () => {
    const secondPageEntry: AuditLogRecord = {
      ...firstEntry,
      audit_reference: "aud-25",
      target_id: "tkt-25",
    };
    api.auditLogs.list.mockImplementation(async (_slug, query: { page?: number } = {}) =>
      page(query.page === 2 ? [secondPageEntry] : [firstEntry], 26, query.page ?? 1),
    );

    renderManagement(<AuditLogsPage />);
    await screen.findByText("ticket.revoked");

    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    expect(await screen.findByText("tkt-25")).toBeInTheDocument();
    expect(api.auditLogs.list).toHaveBeenLastCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 2, page_size: 25 }),
      expect.any(AbortSignal),
    );
  });

  it("is read-only and shows only backend-redacted detail metadata", async () => {
    renderManagement(<AuditLogsPage />);
    await screen.findByText("ticket.revoked");

    expect(screen.queryByRole("button", { name: /Retry|Edit|Delete|Mutate/i })).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: "Details" })[0]);

    expect(await screen.findByText("Audit entry")).toBeInTheDocument();
    expect(screen.getByText("from_status")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.queryByText(/secret-value|password|before_payload/)).toBeNull();
  });

  it.each([
    {
      label: "401",
      error: new ApiError(401, "UNAUTHORIZED", "Sign in again."),
      title: "Authentication required",
      description: "Your session is no longer valid. Sign in again to continue.",
    },
    {
      label: "403",
      error: new ApiError(403, "FORBIDDEN", "Admin access required."),
      title: "Access restricted",
      description: "You do not have permission to manage this event.",
    },
    {
      label: "404",
      error: new ApiError(404, "NOT_FOUND", "Unknown event."),
      title: "Not found",
      description: "Unknown event.",
    },
    {
      label: "422",
      error: new ApiError(422, "VALIDATION_ERROR", "Invalid filter."),
      title: "Invalid request",
      description: "Invalid filter.",
    },
    {
      label: "429",
      error: new ApiError(429, "TOO_MANY_REQUESTS", "Slow down.", [
        { retry_after_seconds: 5 },
      ]),
      title: "Too many requests",
      description: "Please retry in 5 seconds.",
    },
    {
      label: "network",
      error: new Error("Network request failed"),
      title: "Network error",
      description: "Network request failed",
    },
  ])("shows $label failures with the backend message", async ({ error, title, description }) => {
    api.auditLogs.list.mockRejectedValueOnce(error);

    renderManagement(<AuditLogsPage />);

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(description)).toBeInTheDocument();
  });

  it("does not reuse filters or cached data after switching events", async () => {
    const queryClient = createNoRetryQueryClient();
    const view = renderManagement(
      <QueryClientProvider client={queryClient}>
        <AuditLogsPage />
      </QueryClientProvider>,
      queryClient,
    );
    await screen.findByText("ticket.revoked");

    fireEvent.change(screen.getByLabelText("Action"), {
      target: { value: "ticket.revoked" },
    });
    await waitFor(() => {
      expect(api.auditLogs.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ action: "ticket.revoked" }),
        expect.any(AbortSignal),
      );
    });

    params.eventSlug = "other-event";
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <AuditLogsPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(api.auditLogs.list).toHaveBeenLastCalledWith(
        "other-event",
        expect.objectContaining({ action: undefined }),
        expect.any(AbortSignal),
      );
    });
    expect(screen.getByLabelText("Action")).toHaveValue("");
  });

  it("exposes accessible, responsive, read-only controls", async () => {
    renderManagement(<AuditLogsPage />);
    await screen.findByText("ticket.revoked");

    expect(screen.getByRole("table", { name: "Audit logs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
    expect(screen.getByLabelText("Action").closest("div")?.parentElement?.className).toContain(
      "xl:grid-cols-3",
    );
    expect(screen.getAllByRole("button", { name: "Details" }).length).toBeGreaterThan(0);
  });
});
