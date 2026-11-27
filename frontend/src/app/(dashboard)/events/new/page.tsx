"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { EventForm } from "@/components/management/event-form";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { useEventSelection } from "@/components/layout/event-selection-context";
import { useApiClient } from "@/components/providers/api-client-provider";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import {
  valuesToEventCreate,
  type EventFormValues,
} from "@/lib/management/event-form";

export default function NewEventPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const router = useRouter();
  const { selectEvent } = useEventSelection();

  const createMutation = useMutation({
    mutationFn: (values: EventFormValues) =>
      api.events.create(valuesToEventCreate(values)),
    onSuccess: async (event) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: managementKeys.eventsAll() }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      ]);
      selectEvent(event.slug);
      toast.success("Event created", { description: `${event.name} is ready for configuration.` });
      router.push(`/events/${encodeURIComponent(event.slug)}`);
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <ManagementPageHeader
        eyebrow="Administration"
        title="Create event"
        description="Configure the event timeline, venue, capacity, and registration window."
      />
      <EventForm
        mode="create"
        submitLabel="Create event"
        onSubmit={async (values) => {
          await createMutation.mutateAsync(values);
        }}
      />
    </div>
  );
}
