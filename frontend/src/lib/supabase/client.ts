import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { isSupabaseConfigured, getSupabasePublicConfig } from "@/lib/env";

let browserClient: SupabaseClient | null = null;

export function getBrowserSupabaseClient(): SupabaseClient | null {
  if (!isSupabaseConfigured()) {
    return null;
  }

  if (!browserClient) {
    const { url, publishableKey } = getSupabasePublicConfig();
    browserClient = createBrowserClient(url, publishableKey);
  }

  return browserClient;
}

export async function getBrowserAccessToken(): Promise<string | null> {
  const client = getBrowserSupabaseClient();
  if (!client) {
    return null;
  }

  const { data, error } = await client.auth.getSession();
  if (error) {
    return null;
  }

  return data.session?.access_token ?? null;
}
