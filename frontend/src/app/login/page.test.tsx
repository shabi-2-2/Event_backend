import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`);
  }),
  getUser: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

vi.mock("@/lib/env", () => ({ isSupabaseConfigured: () => true }));

vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: vi.fn(async () => ({
    auth: { getUser: mocks.getUser },
  })),
}));

vi.mock("@/components/auth/login-form", () => ({
  LoginForm: ({ next }: { next: string }) => (
    <div data-testid="login-form" data-next={next} />
  ),
}));

import LoginPage from "@/app/login/page";

function pageElement(params: { next?: string; reason?: string }) {
  return LoginPage({ searchParams: Promise.resolve(params) });
}

async function renderLoginPage(params: { next?: string; reason?: string }) {
  return render(await pageElement(params));
}

describe("login page authentication", () => {
  beforeEach(() => {
    mocks.redirect.mockClear();
    mocks.getUser.mockReset();
  });

  it("shows the expired-session notice and preserves the requested route", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null } });

    await renderLoginPage({ next: "/dashboard", reason: "session_expired" });

    expect(await screen.findByText("Your session expired")).toBeInTheDocument();
    expect(screen.getByTestId("login-form")).toHaveAttribute("data-next", "/dashboard");
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("redirects an already authenticated user to the safe next path", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { id: "user-1" } } });

    await expect(pageElement({ next: "/events", reason: "session_expired" })).rejects.toThrow(
      "REDIRECT:/events",
    );

    expect(mocks.redirect).toHaveBeenCalledWith("/events");
  });

  it("does not follow an external next path", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null } });

    await renderLoginPage({ next: "https://evil.example" });

    expect(await screen.findByTestId("login-form")).toHaveAttribute("data-next", "/dashboard");
    expect(mocks.redirect).not.toHaveBeenCalled();
  });
});
