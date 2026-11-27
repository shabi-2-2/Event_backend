"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban } from "lucide-react";
import { toast } from "sonner";
import { ConfirmationDialog } from "@/components/management/confirmation-dialog";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { RegistrationDetails } from "@/components/management/registration-details";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import {
  useEventSlugParam,
  useRegistrationReferenceParam,
} from "@/lib/management/route-params";

export default function RegistrationDetailPage() {
  const slug = useEventSlugParam();
  const reference = useRegistrationReferenceParam();
  const api = useApiClient();
  const queryClient = useQueryClient();

  const registrationQuery = useQuery({
    queryKey: managementKeys.registration(slug, reference),
    queryFn: ({ signal }) => api.registrations.get(slug, reference, signal),
    enabled: Boolean(slug) && Boolean(reference),
  });

  const cancelMutation = useMutation({
    mutationFn: () => api.registrations.cancel(slug, reference),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: managementKeys.registration(slug, reference),
        }),
        queryClient.invalidateQueries({
          queryKey: managementKeys.registrationsAll(slug),
        }),
        queryClient.invalidateQueries({ queryKey: managementKeys.attendeesAll(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.ticketsAll(slug) }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      ]);
      toast.success("Registration cancelled");
    },
  });

  const registration = registrationQuery.data;
  const canCancel =
    Boolean(registration) &&
    registration?.registration_status !== "cancelled" &&
    registration?.check_in_status !== "checked_in";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title={registration?.attendee_name ?? "Registration details"}
        description="Registration status, ticket state, and check-in details."
        backHref={`/events/${encodeURIComponent(slug)}/registrations`}
        backLabel="Registrations"
        actions={
          registration && canCancel ? (
            <ConfirmationDialog
              destructive
              title="Cancel this registration?"
              description={`Registration ${registration.registration_reference} will be cancelled. A linked active ticket may be revoked. This cannot be undone.`}
              confirmLabel="Cancel registration"
              confirmDisabled={cancelMutation.isPending}
              onConfirm={() => cancelMutation.mutateAsync()}
              trigger={
                <Button type="button" variant="outline" disabled={cancelMutation.isPending}>
                  <Ban className="h-4 w-4" aria-hidden="true" />
                  Cancel registration
                </Button>
              }
            />
          ) : null
        }
      />

      {registrationQuery.isPending ? (
        <ManagementTableSkeleton title="registration" rows={4} />
      ) : registrationQuery.isError ? (
        <ManagementErrorState
          error={registrationQuery.error}
          onRetry={() => void registrationQuery.refetch()}
        />
      ) : registration ? (
        <>
          {cancelMutation.isError ? (
            <ManagementErrorState error={cancelMutation.error} />
          ) : null}
          <RegistrationDetails registration={registration} />
        </>
      ) : null}
    </div>
  );
}
