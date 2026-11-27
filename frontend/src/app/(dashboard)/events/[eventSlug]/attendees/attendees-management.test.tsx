import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderManagement } from "@/test/management-test-utils";
import { ApiError } from "@/lib/api/errors";
import type { AdminAttendeeRecord, ViewerAttendeeRecord } from "@/lib/api/contracts";

const params = vi.hoisted(() => ({
  eventSlug: "summit-2026",
  attendeeReference: "att-1",
}));

const api = vi.hoisted(() => ({
  attendees: {
    list: vi.fn(),
    get: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/attendees",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import AttendeesPage from "@/app/(dashboard)/events/[eventSlug]/attendees/page";
import AttendeeDetailPage from "@/app/(dashboard)/events/[eventSlug]/attendees/[attendeeReference]/page";

const viewerAttendee: ViewerAttendeeRecord = {
  attendee_reference: "att-1",
  full_name: "Ada Lovelace",
  urn: "URN-001",
  registration_status: "registered",
  ticket_status: "active",
  check_in_status: "pending",
  checked_in_at: null,
};

const adminAttendee: AdminAttendeeRecord = {
  ...viewerAttendee,
  email: "ada@example.com",
  phone: "+15551234567",
  registration_reference: "reg-1",
  registered_at: "2026-06-01T00:00:00Z",
  cancelled_at: null,
  ticket_reference: "tkt-1",
  ticket_expires_at: null,
  ticket_used_at: null,
  check_in_at: null,
  station: null,
};

function page(items: AdminAttendeeRecord[] | ViewerAttendeeRecord[]) {
  return { items, page: 1, page_size: 25, total: items.length };
}

describe("attendee management", () => {
  beforeEach(() => {
    api.attendees.list.mockReset();
    api.attendees.get.mockReset();
    api.attendees.list.mockResolvedValue(page([viewerAttendee]));
    api.attendees.get.mockResolvedValue(viewerAttendee);
  });

  it("lists attendees and applies backend-supported filters", async () => {
    renderManagement(<AttendeesPage />);

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(api.attendees.list).toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 1, page_size: 25 }),
      expect.any(AbortSignal),
    );

    fireEvent.change(screen.getByLabelText("Search name or URN"), {
      target: { value: "ada" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply search" }));

    await waitFor(() => {
      expect(api.attendees.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ search: "ada", page: 1 }),
        expect.any(AbortSignal),
      );
    });

    fireEvent.change(screen.getByLabelText("Ticket status"), {
      target: { value: "active" },
    });
    await waitFor(() => {
      expect(api.attendees.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ ticket_status: "active" }),
        expect.any(AbortSignal),
      );
    });
  });

  it("does not expose the email filter to viewers", async () => {
    renderManagement(<AttendeesPage />);
    await screen.findByText("Ada Lovelace");
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  it("exposes the email filter only for admin-shaped responses", async () => {
    api.attendees.list.mockResolvedValue(page([adminAttendee]));
    renderManagement(<AttendeesPage />);
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("shows a restricted-field notice in the viewer detail view", async () => {
    renderManagement(<AttendeeDetailPage />);

    expect((await screen.findAllByText("Ada Lovelace")).length).toBeGreaterThan(0);
    expect(screen.getByText(/restricted attendee view/i)).toBeInTheDocument();
    expect(screen.queryByText("ada@example.com")).toBeNull();
    expect(screen.queryByText("+15551234567")).toBeNull();
    expect(screen.queryByText("tkt-1")).toBeNull();
  });

  it("shows admin fields only when the backend returns them", async () => {
    api.attendees.get.mockResolvedValue(adminAttendee);
    renderManagement(<AttendeeDetailPage />);

    expect((await screen.findAllByText("ada@example.com")).length).toBeGreaterThan(0);
    expect(screen.getByText("+15551234567")).toBeInTheDocument();
    expect(screen.getByText("tkt-1")).toBeInTheDocument();
    expect(screen.queryByText(/restricted attendee view/i)).toBeNull();
    expect(screen.queryByText(/token_hash|token_hash=|qr_payload/i)).toBeNull();
  });

  it("handles 403, 404, and network errors", async () => {
    api.attendees.get.mockRejectedValueOnce(
      new ApiError(403, "FORBIDDEN", "You do not have permission."),
    );
    const forbidden = renderManagement(<AttendeeDetailPage />);
    expect(await screen.findByText("Access restricted")).toBeInTheDocument();
    forbidden.unmount();

    api.attendees.get.mockRejectedValueOnce(
      new ApiError(404, "NOT_FOUND", "Attendee not found."),
    );
    const missing = renderManagement(<AttendeeDetailPage />);
    expect(await screen.findByText("Not found")).toBeInTheDocument();
    missing.unmount();

    api.attendees.get.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderManagement(<AttendeeDetailPage />);
    expect(await screen.findByText("Network error")).toBeInTheDocument();
  });
});
