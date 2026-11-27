"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, MapPin, Users } from "lucide-react";
import Link from "next/link";
import { EventStatusBadge } from "@/components/events/event-status-badge";
import { useEventSelection } from "@/components/layout/event-selection-context";
import { useApiClient } from "@/components/providers/api-client-provider";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatDate } from "@/lib/format";

export default function DashboardPage() {
  const { user } = useAuth();
  const api = useApiClient();
  const { selectedEventSlug, selectEvent } = useEventSelection();
  const eventQuery = useQuery({
    queryKey: ["event", selectedEventSlug],
    queryFn: ({ signal }) => api.events.get(selectedEventSlug as string, signal),
    enabled: Boolean(selectedEventSlug),
  });

  const greeting = user?.user_metadata?.full_name ?? user?.email?.split("@")[0] ?? "there";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Overview
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Good day, {greeting}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Select an event to review its details and current status.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/events">Browse events</Link>
        </Button>
      </div>

      {!selectedEventSlug ? (
        <EmptyState
          icon={CalendarDays}
          title="No event selected"
          description="Choose an event from the event list to see its details here. Event selection is stored in the URL, not in browser storage."
          action={
            <Button asChild>
              <Link href="/events">Go to events</Link>
            </Button>
          }
        />
      ) : eventQuery.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
        </div>
      ) : eventQuery.isError ? (
        <ErrorState error={eventQuery.error} onRetry={() => void eventQuery.refetch()} />
      ) : eventQuery.data ? (
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
              <div>
                <CardTitle className="text-xl">{eventQuery.data.name}</CardTitle>
                <CardDescription className="mt-1 font-mono text-xs">
                  {eventQuery.data.slug}
                </CardDescription>
              </div>
              <EventStatusBadge status={eventQuery.data.status} />
            </CardHeader>
            <CardContent className="grid gap-5 sm:grid-cols-2">
              <Detail icon={Clock3} label="Event starts" value={formatDateTime(eventQuery.data.starts_at)} />
              <Detail icon={Clock3} label="Event ends" value={formatDateTime(eventQuery.data.ends_at)} />
              <Detail icon={MapPin} label="Venue" value={eventQuery.data.venue ?? "Not set"} />
              <Detail icon={Users} label="Capacity" value={eventQuery.data.capacity?.toLocaleString() ?? "Unlimited"} />
              <Detail icon={CalendarDays} label="Timezone" value={eventQuery.data.timezone} />
              <Detail
                icon={CalendarDays}
                label="Registration window"
                value={
                  eventQuery.data.registration_opens_at || eventQuery.data.registration_closes_at
                    ? `${formatDate(eventQuery.data.registration_opens_at)} – ${formatDate(eventQuery.data.registration_closes_at)}`
                    : "Not configured"
                }
              />
            </CardContent>
          </Card>

          {eventQuery.data.description ? (
            <Card>
              <CardHeader>
                <CardTitle>Description</CardTitle>
              </CardHeader>
              <CardContent className="text-sm leading-6 text-muted-foreground">
                {eventQuery.data.description}
              </CardContent>
            </Card>
          ) : null}

          <Button variant="ghost" size="sm" onClick={() => selectEvent(null)}>
            Clear selected event
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function Detail({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Clock3;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 text-sm text-foreground">{value}</p>
      </div>
    </div>
  );
}
