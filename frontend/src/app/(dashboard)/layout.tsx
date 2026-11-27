import { redirect } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { ConfigurationRequired } from "@/components/configuration-required";
import { AppShell } from "@/components/layout/app-shell";
import { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { isApiBaseUrlConfigured, isSupabaseConfigured } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  if (!isSupabaseConfigured()) {
    return <ConfigurationRequired />;
  }

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (!user || error) {
    redirect("/login?next=%2Fdashboard");
  }

  // The event list is the only endpoint that verifies global event.manage access.
  // If it cannot be verified, navigation stays closed and the backend remains authoritative.
  let canManageEvents = false;

  if (isApiBaseUrlConfigured()) {
    const { data } = await supabase.auth.getSession();
    const accessToken = data.session?.access_token ?? null;
    const api = new ApiClient(async () => accessToken);

    try {
      await api.events.list({ page: 1, page_size: 1 });
      canManageEvents = true;
    } catch (caught) {
      if (caught instanceof ApiError && caught.isUnauthorized) {
        redirect("/login?reason=session_expired&next=%2Fdashboard");
      }
    }
  }

  return (
    <Suspense fallback={<div className="min-h-screen bg-background" aria-busy="true" />}>
      <AppShell
        user={{
          id: user.id,
          email: user.email,
          name: (user.user_metadata?.full_name as string | undefined) ?? null,
        }}
        canManageEvents={canManageEvents}
      >
        {children}
      </AppShell>
    </Suspense>
  );
}
