import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`);
  }),
  getUser: vi.fn(),
  getSession: vi.fn(),
  eventsList: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

vi.mock("@/lib/env", () => ({
  isSupabaseConfigured: () => true,
  isApiBaseUrlConfigured: () => true,
}));

vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: vi.fn(async () => ({
    auth: { getUser: mocks.getUser, getSession: mocks.getSession },
  })),
}));

vi.mock("@/lib/api/client", () => ({
  ApiClient: class {
    events = { list: mocks.eventsList };
  },
}));

vi.mock("@/components/layout/app-shell", () => ({
  AppShell: ({
    children,
    canManageEvents,
  }: {
    children: ReactNode;
    canManageEvents: boolean;
  }) => (
    <div data-testid="shell" data-can-manage={String(canManageEvents)}>
      {children}
    </div>
  ),
}));

import DashboardLayout from "@/app/(dashboard)/layout";

const user = {
  id: "user-1",
  email: "admin@example.com",
  user_metadata: { full_name: "Admin" },
};

async function renderLayout() {
  return render(
    await DashboardLayout({
      children: <div data-testid="dashboard-content">Dashboard content</div>,
    }),
  );
}

describe("dashboard layout authentication", () => {
  beforeEach(() => {
    mocks.redirect.mockClear();
    mocks.getUser.mockReset();
    mocks.getSession.mockReset();
    mocks.eventsList.mockReset();
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "test-token" } },
      error: null,
    });
  });

  it("redirects unauthenticated visitors to login without calling the backend", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null }, error: null });

    await expect(renderLayout()).rejects.toThrow("REDIRECT:/login?next=%2Fdashboard");

    expect(mocks.redirect).toHaveBeenCalledWith("/login?next=%2Fdashboard");
    expect(mocks.eventsList).not.toHaveBeenCalled();
  });

  it("redirects invalid or expired Supabase sessions", async () => {
    mocks.getUser.mockResolvedValue({
      data: { user: null },
      error: { name: "AuthSessionMissingError" },
    });

    await expect(renderLayout()).rejects.toThrow("REDIRECT:/login?next=%2Fdashboard");

    expect(mocks.redirect).toHaveBeenCalledTimes(1);
    expect(mocks.eventsList).not.toHaveBeenCalled();
  });

  it("renders the dashboard for a verified Supabase user with backend access", async () => {
    mocks.getUser.mockResolvedValue({ data: { user }, error: null });
    mocks.eventsList.mockResolvedValue({ items: [], page: 1, page_size: 1, total: 0 });

    await renderLayout();

    expect(await screen.findByTestId("dashboard-content")).toBeInTheDocument();
    expect(screen.getByTestId("shell")).toHaveAttribute("data-can-manage", "true");
    expect(mocks.redirect).not.toHaveBeenCalled();
    expect(mocks.eventsList).toHaveBeenCalledTimes(1);
  });

  it("does not bounce an authenticated user to login when the backend returns 401", async () => {
    mocks.getUser.mockResolvedValue({ data: { user }, error: null });
    mocks.eventsList.mockRejectedValue(
      new ApiError(401, "UNAUTHORIZED", "Authentication is required."),
    );

    await renderLayout();

    expect(await screen.findByTestId("dashboard-content")).toBeInTheDocument();
    expect(screen.getByTestId("shell")).toHaveAttribute("data-can-manage", "false");
    expect(mocks.redirect).not.toHaveBeenCalled();
    expect(mocks.eventsList).toHaveBeenCalledTimes(1);
  });

  it("keeps management navigation closed when the backend denies access", async () => {
    mocks.getUser.mockResolvedValue({ data: { user }, error: null });
    mocks.eventsList.mockRejectedValue(
      new ApiError(403, "FORBIDDEN", "You do not have access to this resource."),
    );

    await renderLayout();

    expect(await screen.findByTestId("dashboard-content")).toBeInTheDocument();
    expect(screen.getByTestId("shell")).toHaveAttribute("data-can-manage", "false");
    expect(mocks.redirect).not.toHaveBeenCalled();
  });
});
