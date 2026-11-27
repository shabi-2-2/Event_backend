import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { User } from "@supabase/supabase-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
  signOut: vi.fn(),
  fetch: vi.fn(),
  onAuthStateChange: vi.fn(() => ({
    data: { subscription: { unsubscribe: vi.fn() } },
  })),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

vi.mock("@/lib/supabase/client", () => ({
  getBrowserSupabaseClient: () => ({
    auth: { signOut: mocks.signOut, onAuthStateChange: mocks.onAuthStateChange },
  }),
}));

import { AuthProvider, useAuth } from "@/components/providers/auth-provider";

function SignOutButton() {
  const { signOut } = useAuth();
  return <button onClick={() => void signOut()}>Sign out</button>;
}

describe("AuthProvider logout", () => {
  beforeEach(() => {
    mocks.replace.mockReset();
    mocks.refresh.mockReset();
    mocks.signOut.mockReset();
    mocks.fetch.mockReset();
    mocks.onAuthStateChange.mockClear();
    mocks.fetch.mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", mocks.fetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("clears the server session, browser session, and returns to login", async () => {
    render(
      <AuthProvider configured initialUser={{ id: "user-1" } as unknown as User}>
        <SignOutButton />
      </AuthProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(mocks.fetch).toHaveBeenCalledWith("/auth/logout", { method: "POST" });
      expect(mocks.signOut).toHaveBeenCalledTimes(1);
      expect(mocks.replace).toHaveBeenCalledWith("/login");
      expect(mocks.refresh).toHaveBeenCalledTimes(1);
    });
  });

  it("still clears the browser session when the server logout request fails", async () => {
    mocks.fetch.mockRejectedValueOnce(new Error("offline"));

    render(
      <AuthProvider configured initialUser={{ id: "user-1" } as unknown as User}>
        <SignOutButton />
      </AuthProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(mocks.signOut).toHaveBeenCalledTimes(1);
      expect(mocks.replace).toHaveBeenCalledWith("/login");
      expect(mocks.refresh).toHaveBeenCalledTimes(1);
    });
  });
});
