"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, MapPin } from "lucide-react";
import { useState } from "react";
import { EventStatusBadge } from "@/components/events/event-status-badge";
import { useEventSelection } from "@/components/layout/event-selection-context";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { EventStatus } from "@/lib/api/contracts";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 12;

const STATUS_OPTIONS: Array<{ value: EventStatus | "all"; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
  { value: "cancelled", label: "Cancelled" },
];

export default function EventsPage() {
  const api = useApiClient();
  const { selectedEventSlug, selectEvent } = useEventSelection();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<EventStatus | "all">("all");

  const eventsQuery = useQuery({
    queryKey: ["events", { page, page_size: PAGE_SIZE, status }],
    queryFn: ({ signal }) =>
      api.events.list(
        {
          page,
          page_size: PAGE_SIZE,
          status: status === "all" ? undefined : status,
        },
        signal,
      ),
  });

  const events = eventsQuery.data?.items ?? [];
  const totalPages = eventsQuery.data
    ? Math.max(1, Math.ceil(eventsQuery.data.total / PAGE_SIZE))
    : 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Events
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Event list</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Select an event to use it across the workspace.
          </p>
        </div>

        <div className="w-full sm:w-56">
          <Select
            value={status}
            aria-label="Filter events by status"
            onChange={(event) => {
              setStatus(event.target.value as EventStatus | "all");
              setPage(1);
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {eventsQuery.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-56" />
          ))}
        </div>
      ) : eventsQuery.isError ? (
        <ErrorState
          error={eventsQuery.error}
          onRetry={() => void eventsQuery.refetch()}
        />
      ) : events.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title="No events found"
          description={
            status === "all"
              ? "There are no events available for your administrator account yet."
              : "No events match the selected status. Try a different filter."
          }
        />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {events.map((event) => {
              const selected = selectedEventSlug === event.slug;

              return (
                <Card
                  key={event.slug}
                  className={cn(
                    "flex flex-col transition-colors",
                    selected && "border-primary/50 ring-2 ring-primary/10",
                  )}
                >
                  <CardHeader className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <CardTitle className="text-base leading-6">{event.name}</CardTitle>
                      <EventStatusBadge status={event.status} />
                    </div>
                    <CardDescription className="font-mono text-xs">{event.slug}</CardDescription>
                  </CardHeader>
                  <CardContent className="mt-auto space-y-3 text-sm">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <CalendarDays className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span>{formatDate(event.starts_at)}</span>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="truncate">{event.venue ?? "Venue not set"}</span>
                    </div>
                    <Button
                      type="button"
                      variant={selected ? "secondary" : "outline"}
                      size="sm"
                      className="mt-2 w-full"
                      onClick={() => selectEvent(event.slug)}
                    >
                      {selected ? "Selected" : "Select event"}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
            <p className="text-xs text-muted-foreground">
              Page {page} of {totalPages} · {eventsQuery.data?.total ?? 0} total
            </p>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page <= 1 || eventsQuery.isFetching}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Previous
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page >= totalPages || eventsQuery.isFetching}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
