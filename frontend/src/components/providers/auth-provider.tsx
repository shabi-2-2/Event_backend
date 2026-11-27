"use client";

import type { Session, User } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getBrowserSupabaseClient } from "@/lib/supabase/client";

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  configured: boolean;
  refreshUser: () => Promise<User | null>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  configured,
  initialUser = null,
}: {
  children: ReactNode;
  configured: boolean;
  initialUser?: User | null;
}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(initialUser);
  const [isLoading, setIsLoading] = useState(configured && !initialUser);

  const refreshUser = useCallback(async () => {
    const client = getBrowserSupabaseClient();

    if (!client) {
      setUser(null);
      setIsLoading(false);
      return null;
    }

    const { data, error } = await client.auth.getUser();
    setUser(error ? null : (data.user ?? null));
    setIsLoading(false);
    return error ? null : (data.user ?? null);
  }, []);

  const syncSession = useCallback((session: Session | null) => {
    setUser(session?.user ?? null);
    setIsLoading(false);
  }, []);

  useEffect(() => {
    if (!configured) {
      return;
    }

    const client = getBrowserSupabaseClient();
    if (!client) {
      return;
    }

    const { data } = client.auth.onAuthStateChange((event, session) => {
      if (
        event === "INITIAL_SESSION" ||
        event === "SIGNED_IN" ||
        event === "TOKEN_REFRESHED" ||
        event === "USER_UPDATED"
      ) {
        syncSession(session);
      }

      if (event === "SIGNED_OUT") {
        setUser(null);
        setIsLoading(false);
      }
    });

    return () => data.subscription.unsubscribe();
  }, [configured, syncSession]);

  const signOut = useCallback(async () => {
    try {
      await fetch("/auth/logout", { method: "POST" });
    } catch {
      // The browser client fallback still clears local session cookies.
    }

    await getBrowserSupabaseClient()?.auth.signOut();
    setUser(null);
    router.replace("/login");
    router.refresh();
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, configured, refreshUser, signOut }),
    [user, isLoading, configured, refreshUser, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }

  return context;
}
