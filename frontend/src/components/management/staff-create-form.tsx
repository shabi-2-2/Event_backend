"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { StaffCreateRequest } from "@/lib/api/contracts";

const staffCreateSchema = z.object({
  user_id: z.string().trim().uuid("Enter a valid Supabase user UUID."),
  role: z.enum(["admin", "checkin", "viewer"]),
});

type StaffCreateValues = z.infer<typeof staffCreateSchema>;

export function StaffCreateForm({
  onCreate,
  isCreating,
}: {
  onCreate: (body: StaffCreateRequest) => Promise<unknown>;
  isCreating: boolean;
}) {
  const [submitError, setSubmitError] = useState<unknown | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<StaffCreateValues>({
    resolver: zodResolver(staffCreateSchema),
    defaultValues: { user_id: "", role: "viewer" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      await onCreate({ user_id: values.user_id.trim(), role: values.role });
      reset({ user_id: "", role: "viewer" });
    } catch (error) {
      setSubmitError(error);
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add staff member</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {submitError ? <ManagementErrorState error={submitError} /> : null}
          <FormField label="User ID" htmlFor="staff-user-id" error={errors.user_id?.message} hint="The Supabase auth.users UUID. Accounts must already exist.">
            <Input
              id="staff-user-id"
              className="font-mono"
              placeholder="00000000-0000-4000-8000-000000000000"
              aria-invalid={Boolean(errors.user_id)}
              aria-describedby={errors.user_id ? "staff-user-id-error" : undefined}
              {...register("user_id")}
            />
          </FormField>
          <FormField label="Role" htmlFor="staff-role" error={errors.role?.message}>
            <Select
              id="staff-role"
              aria-invalid={Boolean(errors.role)}
              aria-describedby={errors.role ? "staff-role-error" : undefined}
              {...register("role")}
            >
              <option value="admin">Admin</option>
              <option value="checkin">Check-in</option>
              <option value="viewer">Viewer</option>
            </Select>
          </FormField>
          <Button type="submit" disabled={isCreating}>
            {isCreating ? "Adding…" : "Add staff member"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
