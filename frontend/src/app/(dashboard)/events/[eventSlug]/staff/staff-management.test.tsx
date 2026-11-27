import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderManagement } from "@/test/management-test-utils";
import { ApiError } from "@/lib/api/errors";
import type { StaffRecord } from "@/lib/api/contracts";

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  staff: {
    list: vi.fn(),
    create: vi.fn(),
    updateRole: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/staff",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import StaffPage from "@/app/(dashboard)/events/[eventSlug]/staff/page";

const admin: StaffRecord = {
  user_id: "11111111-1111-4111-8111-111111111111",
  role: "admin",
  created_at: "2026-05-01T00:00:00Z",
};

const viewer: StaffRecord = {
  user_id: "22222222-2222-4222-8222-222222222222",
  role: "viewer",
  created_at: "2026-05-02T00:00:00Z",
};

function page(items: StaffRecord[]) {
  return { items, page: 1, page_size: 25, total: items.length };
}

describe("staff management", () => {
  beforeEach(() => {
    api.staff.list.mockReset();
    api.staff.create.mockReset();
    api.staff.updateRole.mockReset();
    api.staff.remove.mockReset();
    api.staff.list.mockResolvedValue(page([admin, viewer]));
    api.staff.create.mockResolvedValue(viewer);
    api.staff.updateRole.mockResolvedValue({ ...viewer, role: "admin" });
    api.staff.remove.mockResolvedValue(undefined);
  });

  it("lists staff and applies the role filter", async () => {
    renderManagement(<StaffPage />);

    expect(await screen.findByText(admin.user_id)).toBeInTheDocument();
    expect(api.staff.list).toHaveBeenCalledWith(
      "summit-2026",
      expect.objectContaining({ page: 1, page_size: 25 }),
      expect.any(AbortSignal),
    );

    fireEvent.change(screen.getByLabelText("Filter staff by role"), {
      target: { value: "checkin" },
    });
    await waitFor(() => {
      expect(api.staff.list).toHaveBeenLastCalledWith(
        "summit-2026",
        expect.objectContaining({ role: "checkin" }),
        expect.any(AbortSignal),
      );
    });
  });

  it("validates the staff create form before calling the API", async () => {
    renderManagement(<StaffPage />);
    await screen.findByText(admin.user_id);

    fireEvent.change(screen.getByLabelText("User ID"), {
      target: { value: "not-a-uuid" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add staff member" }));

    expect(await screen.findByText(/valid Supabase user UUID/)).toBeInTheDocument();
    expect(api.staff.create).not.toHaveBeenCalled();
  });

  it("creates a staff member with a valid UUID", async () => {
    renderManagement(<StaffPage />);
    await screen.findByText(admin.user_id);

    fireEvent.change(screen.getByLabelText("User ID"), {
      target: { value: viewer.user_id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add staff member" }));

    await waitFor(() => {
      expect(api.staff.create).toHaveBeenCalledWith("summit-2026", {
        user_id: viewer.user_id,
        role: "viewer",
      });
    });
  });

  it("changes a staff role through the backend", async () => {
    renderManagement(<StaffPage />);
    await screen.findByText(admin.user_id);

    fireEvent.change(screen.getByLabelText(`Role for ${viewer.user_id}`), {
      target: { value: "admin" },
    });

    await waitFor(() => {
      expect(api.staff.updateRole).toHaveBeenCalledWith("summit-2026", viewer.user_id, {
        role: "admin",
      });
    });
  });

  it("removes a staff member after confirmation", async () => {
    renderManagement(<StaffPage />);
    await screen.findByText(admin.user_id);

    const removeButtons = screen.getAllByRole("button", { name: "Remove" });
    fireEvent.click(removeButtons[1]);
    const confirmButtons = screen.getAllByRole("button", { name: "Remove member" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(api.staff.remove).toHaveBeenCalledWith("summit-2026", viewer.user_id);
    });
  });

  it("explains the final-admin safeguard on a 409 response", async () => {
    api.staff.remove.mockRejectedValueOnce(
      new ApiError(409, "FINAL_ADMIN", "Cannot remove the final admin."),
    );
    renderManagement(<StaffPage />);
    await screen.findByText(admin.user_id);

    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    const confirmButtons = screen.getAllByRole("button", { name: "Remove member" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    expect(await screen.findByText(/protects the final administrator/)).toBeInTheDocument();
  });
});
