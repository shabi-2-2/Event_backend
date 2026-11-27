"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { EventForm } from "@/components/management/event-form";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useApiClient } from "@/components/providers/api-client-provider";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import { valuesToEventUpdate, type EventFormValues } from "@/lib/management/event-form";
import { useEventSlugParam } from "@/lib/management/route-params";

export default function EditEventPage() {
  const slug = useEventSlugParam();
  const api = useApiClient();
  const queryClient = useQueryClient();

  const eventQuery = useQuery({
    queryKey: managementKeys.event(slug),
    queryFn: ({ signal }) => api.events.get(slug, signal),
    enabled: Boolean(slug),
  });

  const updateMutation = useMutation({
    mutationFn: (values: EventFormValues) =>
      api.events.update(slug, valuesToEventUpdate(values)),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: managementKeys.event(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.eventsAll() }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      ]);
      toast.success("Event updated");
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <ManagementPageHeader
        eyebrow="Event"
        title="Edit event"
        description={eventQuery.data ? eventQuery.data.slug : "Loading event configuration."}
      />

      {eventQuery.isPending ? (
        <ManagementTableSkeleton title="event" rows={3} />
      ) : eventQuery.isError ? (
        <ManagementErrorState
          error={eventQuery.error}
          onRetry={() => void eventQuery.refetch()}
        />
      ) : eventQuery.data ? (
        <EventForm
          mode="edit"
          event={eventQuery.data}
          submitLabel="Save changes"
          onSubmit={async (values) => {
            await updateMutation.mutateAsync(values);
          }}
        />
      ) : null}
    </div>
  );
}
