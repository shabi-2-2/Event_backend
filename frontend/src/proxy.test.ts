import type { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

type Cookie = { name: string; value: string };
type CookieMethods = {
  getAll: () => Cookie[];
  setAll: (values: Array<{ name: string; value: string; options?: object }>) => void;
};
type FakeRequest = {
  cookies: {
    getAll: () => Cookie[];
    set: ReturnType<typeof vi.fn>;
  };
  headers: Headers;
};

const harness = vi.hoisted(() => {
  const responses: Array<{
    request: unknown;
    cookies: { set: ReturnType<typeof vi.fn> };
  }> = [];

  return {
    responses,
    next: vi.fn((options: { request: unknown }) => {
      const response = { request: options.request, cookies: { set: vi.fn() } };
      responses.push(response);
      return response;
    }),
    createServerClient: vi.fn(),
    getUser: vi.fn(),
  };
});

vi.mock("next/server", () => ({ NextResponse: { next: harness.next } }));
vi.mock("@supabase/ssr", () => ({ createServerClient: harness.createServerClient }));

import proxy from "@/proxy";

function requestWithCookies(initial: Cookie[]): FakeRequest {
  const store = new Map(initial.map(({ name, value }) => [name, value]));

  return {
    cookies: {
      getAll: () => Array.from(store, ([name, value]) => ({ name, value })),
      set: vi.fn((name: string, value: string) => {
        store.set(name, value);
      }),
    },
    headers: new Headers(),
  };
}

function captureCookieMethods(): CookieMethods {
  const call = harness.createServerClient.mock.calls[0];
  const options = call?.[2] as { cookies?: CookieMethods } | undefined;
  if (!options?.cookies) {
    throw new Error("Supabase cookie methods were not captured");
  }
  return options.cookies;
}

describe("Supabase SSR proxy", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "publishable-key";
    harness.responses.length = 0;
    harness.next.mockClear();
    harness.createServerClient.mockReset();
    harness.getUser.mockReset();
    harness.createServerClient.mockImplementation(() => ({
      auth: { getUser: harness.getUser },
    }));
  });

  it("passes refreshed cookies to both the request and the response", async () => {
    const refreshed = { name: "sb-access-token", value: "refreshed", options: { path: "/" } };
    harness.getUser.mockImplementation(async () => {
      captureCookieMethods().setAll([refreshed]);
      return { data: { user: { id: "user-1" } }, error: null };
    });
    const request = requestWithCookies([
      { name: "sb-access-token", value: "stale" },
    ]);

    const response = await proxy(request as unknown as NextRequest);

    expect(harness.createServerClient).toHaveBeenCalledWith(
      "https://project.supabase.co",
      "publishable-key",
      expect.objectContaining({ cookies: expect.any(Object) }),
    );
    expect(request.cookies.set).toHaveBeenCalledWith(refreshed.name, refreshed.value);
    expect(harness.next).toHaveBeenCalledTimes(2);
    expect(harness.next).toHaveBeenLastCalledWith({ request });
    expect(response.cookies.set).toHaveBeenCalledWith(
      refreshed.name,
      refreshed.value,
      refreshed.options,
    );
    expect((response as unknown as { request: unknown }).request).toBe(request);
  });

  it("propagates cookie removal for invalid or expired sessions", async () => {
    harness.getUser.mockImplementation(async () => {
      captureCookieMethods().setAll([
        { name: "sb-access-token", value: "", options: { maxAge: 0, path: "/" } },
      ]);
      return { data: { user: null }, error: { name: "AuthSessionMissingError" } };
    });
    const request = requestWithCookies([
      { name: "sb-access-token", value: "expired" },
    ]);

    const response = await proxy(request as unknown as NextRequest);

    expect(request.cookies.set).toHaveBeenCalledWith("sb-access-token", "");
    expect(response.cookies.set).toHaveBeenCalledWith("sb-access-token", "", {
      maxAge: 0,
      path: "/",
    });
    expect(harness.next).toHaveBeenCalledTimes(2);
  });

  it("does not create a Supabase client when configuration is incomplete", async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    const request = requestWithCookies([]);

    const response = await proxy(request as unknown as NextRequest);

    expect(harness.createServerClient).not.toHaveBeenCalled();
    expect(harness.next).toHaveBeenCalledTimes(1);
    expect(response.cookies.set).not.toHaveBeenCalled();
  });
});
