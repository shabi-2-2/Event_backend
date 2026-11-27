"use client";

import { useQuery } from "@tanstack/react-query";
import { UserRound } from "lucide-react";
import { AttendeeDetails } from "@/components/management/attendee-details";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useApiClient } from "@/components/providers/api-client-provider";
import { managementKeys } from "@/lib/api/query-keys";
import {
  useAttendeeReferenceParam,
  useEventSlugParam,
} from "@/lib/management/route-params";

export default function AttendeeDetailPage() {
  const slug = useEventSlugParam();
  const reference = useAttendeeReferenceParam();
  const api = useApiClient();

  const attendeeQuery = useQuery({
    queryKey: managementKeys.attendee(slug, reference),
    queryFn: ({ signal }) => api.attendees.get(slug, reference, signal),
    enabled: Boolean(slug) && Boolean(reference),
  });

  const attendee = attendeeQuery.data;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title={attendee?.full_name ?? "Attendee details"}
        description="Authorized attendee fields only. Backend privacy rules determine which fields are visible."
        backHref={`/events/${encodeURIComponent(slug)}/attendees`}
        backLabel="Attendees"
      />

      {attendeeQuery.isPending ? (
        <ManagementTableSkeleton title="attendee" rows={4} />
      ) : attendeeQuery.isError ? (
        <ManagementErrorState
          error={attendeeQuery.error}
          onRetry={() => void attendeeQuery.refetch()}
        />
      ) : attendee ? (
        <AttendeeDetails attendee={attendee} />
      ) : (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-10 text-center">
          <UserRound className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm font-medium">No attendee data available</p>
        </div>
      )}
    </div>
  );
}
