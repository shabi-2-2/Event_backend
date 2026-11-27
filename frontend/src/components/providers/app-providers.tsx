"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ApiClientProvider } from "@/components/providers/api-client-provider";
import { AuthProvider } from "@/components/providers/auth-provider";
import { Toaster } from "@/components/ui/toaster";
import { createAppQueryClient, setUnauthorizedHandler } from "@/lib/api/query-client";

export function AppProviders({
  children,
  supabaseConfigured,
}: {
  children: ReactNode;
  supabaseConfigured: boolean;
}) {
  const router = useRouter();
  const handledRef = useRef(false);
  const [queryClient] = useState(() => createAppQueryClient());

  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (handledRef.current) {
        return;
      }

      handledRef.current = true;
      toast.error("Your session has expired. Please sign in again.");
      void fetch("/auth/logout", { method: "POST" }).catch(() => undefined);
      router.replace("/login?reason=session_expired");
      router.refresh();
      window.setTimeout(() => {
        handledRef.current = false;
      }, 1_000);
    });

    return () => setUnauthorizedHandler(null);
  }, [router]);

  return (
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider>
        <AuthProvider configured={supabaseConfigured}>
          {children}
          <Toaster />
        </AuthProvider>
      </ApiClientProvider>
    </QueryClientProvider>
  );
}
