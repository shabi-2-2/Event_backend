import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderManagement } from "@/test/management-test-utils";
import { ApiError } from "@/lib/api/errors";
import type { TicketRecord } from "@/lib/api/contracts";

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  tickets: {
    list: vi.fn(),
    revoke: vi.fn(),
    resend: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/tickets",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import TicketsPage from "@/app/(dashboard)/events/[eventSlug]/tickets/page";

const activeTicket: TicketRecord = {
  ticket_reference: "tkt-1",
  attendee_reference: "att-1",
  attendee_name: "Ada Lovelace",
  registration_status: "registered",
  ticket_status: "active",
  issued_at: "2026-06-01T00:00:00Z",
  expires_at: null,
  used_at: null,
  revoked_at: null,
  check_in_at: null,
};

const usedTicket: TicketRecord = {
  ...activeTicket,
  ticket_reference: "tkt-2",
  ticket_status: "used",
  used_at: "2026-06-03T00:00:00Z",
};

function page(items: TicketRecord[]) {
  return { items, page: 1, page_size: 25, total: items.length };
}

describe("ticket management", () => {
  beforeEach(() => {
    api.tickets.list.mockReset();
    api.tickets.revoke.mockReset();
    api.tickets.resend.mockReset();
    api.tickets.list.mockResolvedValue(page([activeTicket, usedTicket]));
    api.tickets.revoke.mockResolvedValue({ ...activeTicket, ticket_status: "revoked" });
    api.tickets.resend.mockResolvedValue({
      ticket_reference: "tkt-1",
      delivery_reference: "del-1",
      status: "pending",
      resend_sequence: 1,
      message: "Queued",
    });
  });

  it("lists tickets with filters and status badges", async () => {
    renderManagement(<TicketsPage />);

    expect(await screen.findByText("tkt-1")).toBeInTheDocument();
    expect(screen.getAllByText("active").length).toBeGreaterThan(0);
    expect(api.tickets.list).toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 1, page_size: 25 }),
      expect.any(AbortSignal),
    );

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "used" } });
    await waitFor(() => {
      expect(api.tickets.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ ticket_status: "used" }),
        expect.any(AbortSignal),
      );
    });
  });

  it("never renders ticket tokens or QR payloads", async () => {
    renderManagement(<TicketsPage />);
    await screen.findByText("tkt-1");

    expect(screen.queryByText(/token_hash|qr_payload|secret/i)).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Details" })[0]);
    expect(await screen.findByText("Ticket details")).toBeInTheDocument();
    expect(screen.queryByText(/token_hash|qr_payload|secret/i)).toBeNull();
  });

  it("revokes a ticket after confirmation", async () => {
    renderManagement(<TicketsPage />);
    await screen.findByText("tkt-1");

    fireEvent.click(screen.getAllByRole("button", { name: "Revoke" })[0]);
    expect(
      screen.getByText(/will become revoked. This action is recorded/),
    ).toBeInTheDocument();

    const confirmButtons = screen.getAllByRole("button", { name: "Revoke ticket" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(api.tickets.revoke).toHaveBeenCalledWith("summit-2026", "tkt-1");
    });
  });

  it("does not revoke when confirmation is cancelled", async () => {
    renderManagement(<TicketsPage />);
    await screen.findByText("tkt-1");

    fireEvent.click(screen.getAllByRole("button", { name: "Revoke" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(api.tickets.revoke).not.toHaveBeenCalled();
  });

  it("queues a resend through the outbox operation", async () => {
    renderManagement(<TicketsPage />);
    await screen.findByText("tkt-1");

    fireEvent.click(screen.getAllByRole("button", { name: "Resend" })[0]);
    const confirmButtons = screen.getAllByRole("button", { name: "Queue resend" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(api.tickets.resend).toHaveBeenCalledWith("summit-2026", "tkt-1");
    });
  });

  it("prevents revoking used and checked-in tickets", async () => {
    renderManagement(<TicketsPage />);
    await screen.findByText("tkt-2");

    const revokeButtons = screen.getAllByRole("button", { name: "Revoke" });
    expect(revokeButtons[1]).toBeDisabled();
  });

  it("shows a 409 conflict for an invalid resend", async () => {
    api.tickets.resend.mockRejectedValueOnce(
      new ApiError(409, "RESEND_ALREADY_PENDING", "A resend is already pending."),
    );
    renderManagement(<TicketsPage />);
    await screen.findByText("tkt-1");

    fireEvent.click(screen.getAllByRole("button", { name: "Resend" })[0]);
    const confirmButtons = screen.getAllByRole("button", { name: "Queue resend" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    expect(await screen.findByText("A resend is already pending.")).toBeInTheDocument();
  });
});
