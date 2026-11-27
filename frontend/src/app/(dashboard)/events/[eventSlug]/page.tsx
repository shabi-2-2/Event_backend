"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, LayoutDashboard, Send, Settings2, Users } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { ConfirmationDialog } from "@/components/management/confirmation-dialog";
import { EventDetails } from "@/components/management/event-details";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useEventSelection } from "@/components/layout/event-selection-context";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { EventRecord } from "@/lib/api/contracts";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import { useEventSlugParam } from "@/lib/management/route-params";

export default function EventDetailPage() {
  const slug = useEventSlugParam();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const { selectedEventSlug, selectEvent } = useEventSelection();

  const eventQuery = useQuery({
    queryKey: managementKeys.event(slug),
    queryFn: ({ signal }) => api.events.get(slug, signal),
    enabled: Boolean(slug),
  });

  const lifecycleMutation = useMutation({
    mutationFn: async (action: "publish" | "archive") =>
      action === "publish" ? api.events.publish(slug) : api.events.archive(slug),
    onSuccess: async (event: EventRecord, action) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: managementKeys.event(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.eventsAll() }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      ]);
      toast.success(action === "publish" ? "Event published" : "Event archived");
    },
  });

  const event = eventQuery.data;
  const selected = selectedEventSlug === slug;

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow="Event"
        title={event?.name ?? "Event details"}
        description={event ? `${event.slug} · ${event.timezone}` : "Loading event configuration."}
        actions={
          event ? (
            <>
              <Button
                type="button"
                variant={selected ? "secondary" : "outline"}
                onClick={() => selectEvent(slug)}
              >
                <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
                {selected ? "Workspace event" : "Use as workspace event"}
              </Button>
              <Button asChild variant="outline">
                <Link href={`/events/${encodeURIComponent(slug)}/edit`}>
                  <Settings2 className="h-4 w-4" aria-hidden="true" />
                  Edit
                </Link>
              </Button>
              {event.status === "draft" ? (
                <ConfirmationDialog
                  title="Publish this event?"
                  description="Publishing changes the event status to published. It cannot be reverted to draft."
                  confirmLabel="Publish event"
                  onConfirm={() => lifecycleMutation.mutateAsync("publish")}
                  trigger={
                    <Button type="button" disabled={lifecycleMutation.isPending}>
                      <Send className="h-4 w-4" aria-hidden="true" />
                      Publish
                    </Button>
                  }
                />
              ) : null}
              {event.status === "published" ? (
                <ConfirmationDialog
                  destructive
                  title="Archive this event?"
                  description="Archiving changes the event status to archived. Archived events cannot be reopened."
                  confirmLabel="Archive event"
                  onConfirm={() => lifecycleMutation.mutateAsync("archive")}
                  trigger={
                    <Button type="button" variant="outline" disabled={lifecycleMutation.isPending}>
                      <Archive className="h-4 w-4" aria-hidden="true" />
                      Archive
                    </Button>
                  }
                />
              ) : null}
            </>
          ) : null
        }
      />

      {eventQuery.isPending ? (
        <ManagementTableSkeleton title="event" rows={3} />
      ) : eventQuery.isError ? (
        <ManagementErrorState
          error={eventQuery.error}
          onRetry={() => void eventQuery.refetch()}
        />
      ) : event ? (
        <>
          {lifecycleMutation.isError ? (
            <ManagementErrorState error={lifecycleMutation.error} />
          ) : null}
          <EventDetails event={event} />

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[
              { href: "attendees", label: "Attendees", description: "Search and review attendee records.", icon: Users },
              { href: "registrations", label: "Registrations", description: "Review registrations and cancellations.", icon: LayoutDashboard },
              { href: "tickets", label: "Tickets", description: "Revoke tickets or queue email resends.", icon: Send },
              { href: "staff", label: "Staff access", description: "Manage event-scoped roles and memberships.", icon: Settings2 },
            ].map((item) => (
              <Card key={item.href}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <item.icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                    {item.label}
                  </CardTitle>
                  <CardDescription>{item.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/events/${encodeURIComponent(slug)}/${item.href}`}>
                      Open {item.label.toLowerCase()}
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
