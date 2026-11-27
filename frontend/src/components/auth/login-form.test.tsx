import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const signInWithPassword = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();
const toastError = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  getBrowserSupabaseClient: () => ({ auth: { signInWithPassword } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

vi.mock("sonner", () => ({
  toast: { error: toastError },
}));

describe("LoginForm", () => {
  beforeEach(() => {
    signInWithPassword.mockReset();
    replace.mockReset();
    refresh.mockReset();
    toastError.mockReset();
  });

  it("submits credentials and navigates to the requested page", async () => {
    signInWithPassword.mockResolvedValueOnce({
      data: { user: { id: "user-1" }, session: { expires_in: 3600 } },
      error: null,
    });

    const { LoginForm } = await import("@/components/auth/login-form");
    render(<LoginForm configured next="/events?event=demo" />);

    fireEvent.change(screen.getByLabelText(/work email/i), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter your password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalledWith({
        email: "admin@example.com",
        password: "correct-password",
      });
    });
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/events?event=demo");
      expect(refresh).toHaveBeenCalled();
    });
  });

  it("shows a toast and stays on the page when Supabase rejects credentials", async () => {
    signInWithPassword.mockResolvedValueOnce({
      error: { message: "Invalid login credentials" },
    });

    const { LoginForm } = await import("@/components/auth/login-form");
    render(<LoginForm configured next="/dashboard" />);

    fireEvent.change(screen.getByLabelText(/work email/i), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter your password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Sign in failed", {
        description: "Invalid login credentials",
      });
    });
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows validation errors without calling Supabase", async () => {
    const { LoginForm } = await import("@/components/auth/login-form");
    render(<LoginForm configured next="/dashboard" />);

    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Email is required.")).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
    expect(signInWithPassword).not.toHaveBeenCalled();
  });
});
