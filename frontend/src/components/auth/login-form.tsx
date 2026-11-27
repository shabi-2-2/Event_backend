"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { getBrowserSupabaseClient } from "@/lib/supabase/client";

const loginSchema = z.object({
  email: z.string().trim().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginForm({
  configured,
  next,
}: {
  configured: boolean;
  next: string;
}) {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    const supabase = getBrowserSupabaseClient();

    if (!supabase) {
      toast.error("Supabase is not configured for this frontend.");
      return;
    }

    const { error } = await supabase.auth.signInWithPassword(values);

    if (error) {
      toast.error("Sign in failed", { description: error.message });
      return;
    }

    router.replace(next);
    router.refresh();
  });

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      {!configured ? (
        <Alert variant="warning">
          <AlertTitle>Configuration required</AlertTitle>
          <AlertDescription>
            Set the Supabase URL and publishable key in <code>.env.local</code> to enable sign in.
          </AlertDescription>
        </Alert>
      ) : null}

      <FormField
        label="Work email"
        htmlFor="email"
        error={errors.email?.message}
      >
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          disabled={!configured || isSubmitting}
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? "email-error" : undefined}
          {...register("email")}
        />
      </FormField>

      <FormField
        label="Password"
        htmlFor="password"
        error={errors.password?.message}
      >
        <Input
          id="password"
          type={showPassword ? "text" : "password"}
          autoComplete="current-password"
          placeholder="Enter your password"
          disabled={!configured || isSubmitting}
          aria-invalid={Boolean(errors.password)}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...register("password")}
        />
      </FormField>

      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-input accent-[var(--primary)]"
          checked={showPassword}
          onChange={(event) => setShowPassword(event.target.checked)}
        />
        Show password
      </label>

      <Button type="submit" className="w-full" disabled={!configured || isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
        {!isSubmitting ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
      </Button>
    </form>
  );
}
