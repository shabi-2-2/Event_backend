"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EventTable } from "@/components/management/event-table";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useEventSelection } from "@/components/layout/event-selection-context";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { EventStatus } from "@/lib/api/contracts";
import { managementKeys } from "@/lib/api/query-keys";

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

  const params = {
    page,
    page_size: PAGE_SIZE,
    status: status === "all" ? undefined : status,
  };

  const eventsQuery = useQuery({
    queryKey: managementKeys.events(params),
    queryFn: ({ signal }) => api.events.list(params, signal),
  });

  const events = eventsQuery.data?.items ?? [];
  const total = eventsQuery.data?.total ?? 0;

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow="Administration"
        title="Event list"
        description="Create events, review configuration, and select the workspace event."
        actions={
          <Button asChild>
            <Link href="/events/new">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Create event
            </Link>
          </Button>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
        <p className="text-xs text-muted-foreground">
          Status is managed through publish and archive only. Cancelled is read-only.
        </p>
      </div>

      {eventsQuery.isPending ? (
        <ManagementTableSkeleton title="events" />
      ) : eventsQuery.isError ? (
        <ManagementErrorState
          error={eventsQuery.error}
          onRetry={() => void eventsQuery.refetch()}
        />
      ) : events.length === 0 ? (
        <ManagementEmptyState
          icon={CalendarDays}
          title="No events found"
          description={
            status === "all"
              ? "No events are available for your administrator account yet."
              : "No events match the selected status. Try a different filter."
          }
          action={
            <Button asChild>
              <Link href="/events/new">Create event</Link>
            </Button>
          }
        />
      ) : (
        <>
          <EventTable
            events={events}
            selectedEventSlug={selectedEventSlug}
            onSelectEvent={selectEvent}
          />
          <ManagementPagination
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            isFetching={eventsQuery.isFetching}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
