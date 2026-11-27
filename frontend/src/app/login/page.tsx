import { CalendarCheck2, ShieldCheck } from "lucide-react";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { LoginForm } from "@/components/auth/login-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNextPath } from "@/lib/auth/guards";
import { isSupabaseConfigured } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Sign in",
};

type LoginSearchParams = Promise<{
  next?: string | string[];
  reason?: string | string[];
}>;

export default async function LoginPage({
  searchParams,
}: {
  searchParams: LoginSearchParams;
}) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const reason = Array.isArray(params.reason) ? params.reason[0] : params.reason;
  const configured = isSupabaseConfigured();

  if (configured) {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (user) {
      redirect(next);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden border-r border-border bg-primary px-12 py-14 text-primary-foreground lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3 text-sm font-semibold">
          <CalendarCheck2 className="h-5 w-5" aria-hidden="true" />
          Event Operations
        </div>

        <div className="max-w-xl space-y-5">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-primary-foreground/70">
            Admin workspace
          </p>
          <h1 className="text-4xl font-semibold leading-tight tracking-tight">
            Run every event with a clear operational view.
          </h1>
          <p className="text-base leading-7 text-primary-foreground/75">
            Manage events, coordinate staff, and support check-in from one restrained,
            purpose-built workspace.
          </p>
        </div>

        <div className="flex items-center gap-2 text-sm text-primary-foreground/70">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Access is controlled by your event staff role.
        </div>
      </section>

      <section className="flex items-center justify-center bg-background px-6 py-12 sm:px-10">
        <div className="w-full max-w-md space-y-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold lg:hidden">
              <CalendarCheck2 className="h-5 w-5 text-primary" aria-hidden="true" />
              Event Operations
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">Welcome back</h2>
            <p className="text-sm text-muted-foreground">
              Sign in with your Supabase account to continue.
            </p>
          </div>

          {reason === "session_expired" ? (
            <Alert variant="warning">
              <AlertTitle>Your session expired</AlertTitle>
              <AlertDescription>Sign in again to continue where you left off.</AlertDescription>
            </Alert>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Sign in</CardTitle>
              <CardDescription>Use the credentials issued by your event administrator.</CardDescription>
            </CardHeader>
            <CardContent>
              <LoginForm configured={configured} next={next} />
            </CardContent>
          </Card>

          <p className="text-center text-xs text-muted-foreground">
            This application does not expose backend secrets in the browser.
          </p>
        </div>
      </section>
    </main>
  );
}
