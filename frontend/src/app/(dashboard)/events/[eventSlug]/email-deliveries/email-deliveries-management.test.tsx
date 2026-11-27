import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import type { EmailDeliveryRecord, EmailRetryResponse } from "@/lib/api/contracts";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import {
  createNoRetryQueryClient,
  renderManagement,
} from "@/test/management-test-utils";

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  emailDeliveries: {
    list: vi.fn(),
    retry: vi.fn(),
  },
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/email-deliveries",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast }));

import EmailDeliveriesPage from "@/app/(dashboard)/events/[eventSlug]/email-deliveries/page";

const failed: EmailDeliveryRecord = {
  delivery_reference: "del-1",
  registration_reference: "reg-1",
  ticket_reference: "tkt-1",
  purpose: "ticket_issued",
  status: "failed",
  attempts: 2,
  resend_sequence: 0,
  error_code: "SMTP_TIMEOUT",
  next_attempt_at: null,
  created_at: "2026-06-01T10:00:00Z",
  sent_at: null,
};

const deadLetter: EmailDeliveryRecord = {
  ...failed,
  delivery_reference: "del-2",
  ticket_reference: "tkt-2",
  status: "dead_letter",
  attempts: 5,
  resend_sequence: 1,
};

const pending: EmailDeliveryRecord = {
  ...failed,
  delivery_reference: "del-3",
  ticket_reference: "tkt-3",
  status: "pending",
  error_code: null,
};

const sent: EmailDeliveryRecord = {
  ...failed,
  delivery_reference: "del-4",
  ticket_reference: "tkt-4",
  status: "sent",
  error_code: null,
  next_attempt_at: null,
  sent_at: "2026-06-01T10:05:00Z",
};

const retryResult: EmailRetryResponse = {
  delivery_reference: "del-1",
  registration_reference: "reg-1",
  ticket_reference: "tkt-1",
  status: "pending",
  resend_sequence: 1,
  previous_status: "failed",
  message: "Replacement job queued.",
};

function page(items: EmailDeliveryRecord[], total = items.length, pageNumber = 1) {
  return { items, page: pageNumber, page_size: 25, total };
}

function openRetryConfirmation(reference = "del-1") {
  fireEvent.click(screen.getByRole("button", { name: `Retry delivery ${reference}` }));
  return screen.getByRole("button", { name: "Queue retry" });
}

describe("email delivery operations", () => {
  beforeEach(() => {
    params.eventSlug = "summit-2026";
    api.emailDeliveries.list.mockReset().mockResolvedValue(
      page([failed, deadLetter, pending, sent], 4),
    );
    api.emailDeliveries.retry.mockReset().mockResolvedValue(retryResult);
    toast.success.mockReset();
    toast.error.mockReset();
  });

  it("lists deliveries with clear statuses and only eligible retry actions", async () => {
    renderManagement(<EmailDeliveriesPage />);

    expect(await screen.findByText("del-1")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Email deliveries" });
    expect(within(table).getByText("Failed")).toBeInTheDocument();
    expect(within(table).getByText("Dead letter")).toBeInTheDocument();
    expect(within(table).getByText("Pending")).toBeInTheDocument();
    expect(within(table).getByText("Sent")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Retry delivery / })).toHaveLength(2);
    expect(api.emailDeliveries.list).toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 1, page_size: 25 }),
      expect.any(AbortSignal),
    );
  });

  it("maps every supported filter to backend query parameters", async () => {
    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "dead_letter" } });
    fireEvent.change(screen.getByLabelText("Registration reference"), {
      target: { value: "reg-9" },
    });
    fireEvent.change(screen.getByLabelText("Ticket reference"), {
      target: { value: "tkt-9" },
    });
    fireEvent.change(screen.getByLabelText("Minimum attempts"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Maximum attempts"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Error code"), {
      target: { value: "SMTP_TIMEOUT" },
    });
    fireEvent.change(screen.getByLabelText("Next attempt after"), {
      target: { value: "2026-06-01T08:30" },
    });
    fireEvent.change(screen.getByLabelText("Next attempt before"), {
      target: { value: "2026-06-02T08:30" },
    });

    await waitFor(() => {
      expect(api.emailDeliveries.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({
          page: 1,
          status: "dead_letter",
          registration_reference: "reg-9",
          ticket_reference: "tkt-9",
          min_attempts: 2,
          max_attempts: 6,
          error_code: "SMTP_TIMEOUT",
          next_attempt_after: "2026-06-01T08:30:00.000Z",
          next_attempt_before: "2026-06-02T08:30:00.000Z",
        }),
        expect.any(AbortSignal),
      );
    });
  });

  it("rejects invalid filter values before requesting a page", async () => {
    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    fireEvent.change(screen.getByLabelText("Minimum attempts"), { target: { value: "21" } });

    expect(
      screen.getByText(/Attempts must be whole numbers from 0 to 20/),
    ).toBeInTheDocument();
    expect(api.emailDeliveries.list).not.toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ min_attempts: 21 }),
      expect.anything(),
    );
  });

  it("requests the next page without changing filters", async () => {
    const secondPage: EmailDeliveryRecord = {
      ...failed,
      delivery_reference: "del-25",
      ticket_reference: "tkt-25",
      status: "sent",
    };
    api.emailDeliveries.list.mockImplementation(async (_slug, query: { page?: number } = {}) =>
      page(query.page === 2 ? [secondPage] : [failed], 26, query.page ?? 1),
    );

    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    expect(await screen.findByText("del-25")).toBeInTheDocument();
    expect(api.emailDeliveries.list).toHaveBeenLastCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 2, page_size: 25 }),
      expect.any(AbortSignal),
    );
  });

  it("requires confirmation and shows the backend retry result", async () => {
    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    const confirm = openRetryConfirmation();
    expect(screen.getByText("Retry this delivery?")).toBeInTheDocument();
    expect(api.emailDeliveries.retry).not.toHaveBeenCalled();

    fireEvent.click(confirm);

    await waitFor(() => {
      expect(api.emailDeliveries.retry).toHaveBeenCalledWith(
        "summit-2026",
        "del-1",
        expect.any(AbortSignal),
      );
    });
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Delivery retry queued",
        expect.objectContaining({
          description: expect.stringContaining("Replacement job queued."),
        }),
      );
    });
  });

  it("does not retry when confirmation is cancelled", async () => {
    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    openRetryConfirmation();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(api.emailDeliveries.retry).not.toHaveBeenCalled();
  });

  it("prevents duplicate retry submissions while a retry is pending", async () => {
    let resolveRetry: (value: EmailRetryResponse) => void = () => undefined;
    api.emailDeliveries.retry.mockImplementation(
      () =>
        new Promise<EmailRetryResponse>((resolve) => {
          resolveRetry = resolve;
        }),
    );

    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    const confirm = openRetryConfirmation();
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(api.emailDeliveries.retry).toHaveBeenCalledTimes(1);
    });
    resolveRetry(retryResult);
  });

  it("shows backend retry conflicts without altering the list optimistically", async () => {
    api.emailDeliveries.retry.mockRejectedValueOnce(
      new ApiError(409, "RESEND_ALREADY_PENDING", "A retry is already pending."),
    );

    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    fireEvent.click(openRetryConfirmation());

    expect(await screen.findByText("A retry is already pending.")).toBeInTheDocument();
    expect(
      within(screen.getByRole("table", { name: "Email deliveries" })).getByText("Failed"),
    ).toBeInTheDocument();
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
        { retry_after_seconds: 7 },
      ]),
      title: "Too many requests",
      description: "Please retry in 7 seconds.",
    },
    {
      label: "network",
      error: new Error("Network request failed"),
      title: "Network error",
      description: "Network request failed",
    },
  ])("shows $label list failures with the backend message", async ({ error, title, description }) => {
    api.emailDeliveries.list.mockRejectedValueOnce(error);

    renderManagement(<EmailDeliveriesPage />);

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(description)).toBeInTheDocument();
  });

  it("invalidates email, audit, and dashboard queries after a successful retry", async () => {
    const queryClient = createNoRetryQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    renderManagement(
      <QueryClientProvider client={queryClient}>
        <EmailDeliveriesPage />
      </QueryClientProvider>,
      queryClient,
    );
    await screen.findByText("del-1");

    fireEvent.click(openRetryConfirmation());

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: managementKeys.emailDeliveriesAll("summit-2026"),
        }),
      );
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: managementKeys.auditLogsAll("summit-2026") }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: dashboardKeys.emailDeliveries("summit-2026") }),
    );
  });

  it("does not reuse filters or cached data after switching events", async () => {
    const queryClient = createNoRetryQueryClient();
    const view = renderManagement(
      <QueryClientProvider client={queryClient}>
        <EmailDeliveriesPage />
      </QueryClientProvider>,
      queryClient,
    );
    await screen.findByText("del-1");

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "failed" } });
    await waitFor(() => {
      expect(api.emailDeliveries.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ status: "failed" }),
        expect.any(AbortSignal),
      );
    });

    params.eventSlug = "other-event";
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <EmailDeliveriesPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(api.emailDeliveries.list).toHaveBeenLastCalledWith(
        "other-event",
        expect.objectContaining({ status: undefined }),
        expect.any(AbortSignal),
      );
    });
    expect(screen.getByLabelText("Status")).toHaveValue("");
  });

  it("exposes accessible, responsive controls and no provider secrets in details", async () => {
    renderManagement(<EmailDeliveriesPage />);
    await screen.findByText("del-1");

    expect(screen.getByRole("table", { name: "Email deliveries" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
    expect(screen.getByLabelText("Status").closest("div")?.parentElement?.className).toContain(
      "xl:grid-cols-3",
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Details" })[0]);
    expect(await screen.findByText("Email delivery details")).toBeInTheDocument();
    expect(screen.queryByText(/provider-secret|smtp-password|message_body/i)).toBeNull();
  });
});
