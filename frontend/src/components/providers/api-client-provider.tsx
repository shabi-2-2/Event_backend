"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { ApiClient } from "@/lib/api/client";
import { getBrowserAccessToken } from "@/lib/supabase/client";

const ApiClientContext = createContext<ApiClient | null>(null);

export function ApiClientProvider({ children }: { children: ReactNode }) {
  const client = useMemo(() => new ApiClient(getBrowserAccessToken), []);

  return <ApiClientContext.Provider value={client}>{children}</ApiClientContext.Provider>;
}

export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext);

  if (!client) {
    throw new Error("useApiClient must be used within ApiClientProvider.");
  }

  return client;
}
