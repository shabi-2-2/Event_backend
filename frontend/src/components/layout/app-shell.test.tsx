import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const signOut = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
    configured: true,
    refreshUser: vi.fn(),
    signOut,
  }),
}));

describe("AppShell", () => {
  beforeEach(() => {
    replace.mockReset();
    signOut.mockReset();
  });

  it("renders desktop navigation and a mobile navigation trigger", async () => {
    const { AppShell } = await import("@/components/layout/app-shell");

    render(
      <AppShell user={{ id: "user-1", email: "admin@example.com" }} canManageEvents>
        <div>Dashboard content</div>
      </AppShell>,
    );

    expect(screen.getByLabelText("Main navigation")).toBeInTheDocument();
    expect(screen.getAllByText("Dashboard").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Events").length).toBeGreaterThan(0);
    expect(screen.getByText("Dashboard content")).toBeInTheDocument();

    const mobileTrigger = screen.getByRole("button", { name: /open navigation menu/i });
    fireEvent.click(mobileTrigger);

    expect(screen.getByLabelText("Mobile navigation")).toBeInTheDocument();
    expect(screen.getAllByText("Events").length).toBeGreaterThan(1);
  });

  it("hides event-management navigation when the backend did not grant it", async () => {
    const { AppShell } = await import("@/components/layout/app-shell");

    render(
      <AppShell user={{ id: "user-2", email: "viewer@example.com" }} canManageEvents={false}>
        <div>Restricted content</div>
      </AppShell>,
    );

    const mainNav = screen.getByLabelText("Main navigation");
    expect(mainNav).toHaveTextContent("Dashboard");
    expect(mainNav).not.toHaveTextContent("Events");
  });
});
