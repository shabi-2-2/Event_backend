import { beforeEach, describe, expect, it, vi } from "vitest";

const createBrowserClientMock = vi.fn();
const createServerClientMock = vi.fn();
const cookieStore = {
  getAll: vi.fn(() => [{ name: "sb-token", value: "cookie-value" }]),
  set: vi.fn(),
};

vi.mock("@supabase/ssr", () => ({
  createBrowserClient: createBrowserClientMock,
  createServerClient: createServerClientMock,
}));

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => cookieStore),
}));

describe("Supabase clients", () => {
  beforeEach(() => {
    vi.resetModules();
    createBrowserClientMock.mockReset();
    createServerClientMock.mockReset();
    cookieStore.set.mockClear();
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-key";
  });

  it("creates a browser client with only public configuration", async () => {
    const fakeClient = { auth: { getUser: vi.fn() } };
    createBrowserClientMock.mockReturnValue(fakeClient);

    const { getBrowserSupabaseClient } = await import("@/lib/supabase/client");
    const client = getBrowserSupabaseClient();

    expect(createBrowserClientMock).toHaveBeenCalledWith(
      "https://project.supabase.co",
      "publishable-key",
    );
    expect(client).toBe(fakeClient);
    expect(getBrowserSupabaseClient()).toBe(fakeClient);
  });

  it("does not create a browser client when configuration is missing", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

    const { getBrowserSupabaseClient } = await import("@/lib/supabase/client");

    expect(getBrowserSupabaseClient()).toBeNull();
    expect(createBrowserClientMock).not.toHaveBeenCalled();
  });

  it("wires server cookie reads and writes through next/headers", async () => {
    const fakeClient = { auth: { getUser: vi.fn() } };
    createServerClientMock.mockReturnValue(fakeClient);

    const { createSupabaseServerClient } = await import("@/lib/supabase/server");
    const client = await createSupabaseServerClient();

    expect(client).toBe(fakeClient);
    expect(createServerClientMock).toHaveBeenCalledWith(
      "https://project.supabase.co",
      "publishable-key",
      expect.objectContaining({ cookies: expect.any(Object) }),
    );

    const options = createServerClientMock.mock.calls[0][2] as {
      cookies: {
        getAll: () => unknown[];
        setAll: (values: Array<{ name: string; value: string }>) => void;
      };
    };

    expect(options.cookies.getAll()).toEqual([
      { name: "sb-token", value: "cookie-value" },
    ]);
    options.cookies.setAll([{ name: "sb-token", value: "refreshed" }]);
    expect(cookieStore.set).toHaveBeenCalledWith("sb-token", "refreshed", undefined);
  });
});
