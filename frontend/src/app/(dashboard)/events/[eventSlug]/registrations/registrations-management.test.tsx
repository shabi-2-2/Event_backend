import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderManagement } from "@/test/management-test-utils";
import { ApiError } from "@/lib/api/errors";
import type { RegistrationRecord } from "@/lib/api/contracts";

const params = vi.hoisted(() => ({
  eventSlug: "summit-2026",
  registrationReference: "reg-1",
}));

const api = vi.hoisted(() => ({
  registrations: {
    list: vi.fn(),
    get: vi.fn(),
    cancel: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/registrations",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import RegistrationsPage from "@/app/(dashboard)/events/[eventSlug]/registrations/page";
import RegistrationDetailPage from "@/app/(dashboard)/events/[eventSlug]/registrations/[registrationReference]/page";

const registered: RegistrationRecord = {
  registration_reference: "reg-1",
  attendee_reference: "att-1",
  attendee_name: "Ada Lovelace",
  email: "ada@example.com",
  phone: null,
  registration_status: "registered",
  registered_at: "2026-06-01T00:00:00Z",
  checked_in_at: null,
  cancelled_at: null,
  ticket_reference: "tkt-1",
  ticket_status: "active",
  check_in_status: "pending",
  check_in_at: null,
  station: null,
};

const cancelled: RegistrationRecord = {
  ...registered,
  registration_status: "cancelled",
  cancelled_at: "2026-06-02T00:00:00Z",
  ticket_status: "revoked",
};

function page(items: RegistrationRecord[]) {
  return { items, page: 1, page_size: 25, total: items.length };
}

describe("registration management", () => {
  beforeEach(() => {
    api.registrations.list.mockReset();
    api.registrations.get.mockReset();
    api.registrations.cancel.mockReset();
    api.registrations.list.mockResolvedValue(page([registered]));
    api.registrations.get.mockResolvedValue(registered);
    api.registrations.cancel.mockResolvedValue(cancelled);
  });

  it("lists registrations with exact filters and status badges", async () => {
    renderManagement(<RegistrationsPage />);

    expect((await screen.findAllByText("Ada Lovelace")).length).toBeGreaterThan(0);
    expect(screen.getByText("registered")).toBeInTheDocument();
    expect(api.registrations.list).toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 1, page_size: 25 }),
      expect.any(AbortSignal),
    );

    fireEvent.change(screen.getByLabelText("Registration status"), {
      target: { value: "cancelled" },
    });

    await waitFor(() => {
      expect(api.registrations.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ registration_status: "cancelled" }),
        expect.any(AbortSignal),
      );
    });
  });

  it("distinguishes cancelled registrations from declined RSVPs", async () => {
    api.registrations.get.mockResolvedValue(cancelled);
    renderManagement(<RegistrationDetailPage />);

    expect(await screen.findByText("cancelled")).toBeInTheDocument();
    expect(screen.queryByText("declined")).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel registration" })).toBeNull();
  });

  it("cancels a registration only after confirmation and invalidates queries", async () => {
    const view = renderManagement(<RegistrationDetailPage />);
    expect((await screen.findAllByText("Ada Lovelace")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Cancel registration" }));
    expect(
      screen.getByText(/will be cancelled. A linked active ticket may be revoked/),
    ).toBeInTheDocument();

    const confirmButtons = screen.getAllByRole("button", { name: "Cancel registration" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(api.registrations.cancel).toHaveBeenCalledWith("summit-2026", "reg-1");
    });
    expect(api.registrations.get).toHaveBeenCalled();
    view.unmount();
  });

  it("does not call cancel when the confirmation is dismissed", async () => {
    renderManagement(<RegistrationDetailPage />);
    expect((await screen.findAllByText("Ada Lovelace")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Cancel registration" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(api.registrations.cancel).not.toHaveBeenCalled();
  });

  it("shows 409 conflict and 429 error states", async () => {
    api.registrations.cancel.mockRejectedValueOnce(
      new ApiError(409, "CONFLICT", "Registration is already checked in."),
    );
    renderManagement(<RegistrationDetailPage />);
    await screen.findAllByText("Ada Lovelace");
    fireEvent.click(screen.getByRole("button", { name: "Cancel registration" }));
    const confirmButtons = screen.getAllByRole("button", { name: "Cancel registration" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    expect(await screen.findByText("Registration is already checked in.")).toBeInTheDocument();
  });
});
