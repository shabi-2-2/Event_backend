"use client";

import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useState } from "react";
import { AuditLogTable } from "@/components/management/audit-log-table";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { AuditLogListParams, SortOrder } from "@/lib/api/contracts";
import { managementKeys } from "@/lib/api/query-keys";
import { useEventSlugParam } from "@/lib/management/route-params";
import {
  datetimeLocalToUtc,
  isUuid,
} from "@/lib/operations/filters";
import { parseAuditLogPage } from "@/lib/operations/validation";

const PAGE_SIZE = 25;

export default function AuditLogsPage() {
  const slug = useEventSlugParam();

  // Remount on event change so filters and cached pages are never reused for a
  // different event.
  return <AuditLogsWorkspace key={slug} slug={slug} />;
}

function AuditLogsWorkspace({ slug }: { slug: string }) {
  const api = useApiClient();
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [actorUserId, setActorUserId] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  const fromUtc = datetimeLocalToUtc(fromDate);
  const toUtc = datetimeLocalToUtc(toDate);
  const actorInvalid = actorUserId.trim() !== "" && !isUuid(actorUserId);
  const datesInvalid =
    (fromDate.trim() !== "" && fromUtc === undefined) ||
    (toDate.trim() !== "" && toUtc === undefined) ||
    (fromUtc !== undefined && toUtc !== undefined && toUtc < fromUtc);
  const filterError = actorInvalid
    ? "Actor ID must be a Supabase user UUID."
    : datesInvalid
      ? "Enter valid dates in chronological order."
      : null;

  const params: AuditLogListParams = {
    page,
    page_size: PAGE_SIZE,
    action: action.trim() || undefined,
    actor_user_id: actorInvalid ? undefined : actorUserId.trim() || undefined,
    from_date: datesInvalid ? undefined : fromUtc,
    to_date: datesInvalid ? undefined : toUtc,
    sort_order: sortOrder,
  };

  const auditQuery = useQuery({
    queryKey: managementKeys.auditLogs(slug, params),
    queryFn: async ({ signal }) => {
      const raw = await api.auditLogs.list(slug, params, signal);
      const parsed = parseAuditLogPage(raw);
      if (!parsed) {
        throw new Error("The server returned an unexpected audit log response.");
      }
      return parsed;
    },
    enabled: Boolean(slug),
  });

  function resetFilters() {
    setPage(1);
    setAction("");
    setActorUserId("");
    setFromDate("");
    setToDate("");
    setSortOrder("desc");
  }

  const entries = auditQuery.data?.items ?? [];

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title="Audit logs"
        description="Read-only view of backend-recorded administrative actions. Context is limited to the redacted metadata the backend returns."
        backHref={`/events/${encodeURIComponent(slug)}`}
        backLabel="Event"
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ScrollText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            Audit filters
          </CardTitle>
          <CardDescription>
            Date-time filters are entered in your local time and sent as UTC. The backend remains
            the only source of audit records.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <FormField label="Action" htmlFor="audit-action">
              <Input
                id="audit-action"
                value={action}
                maxLength={100}
                placeholder="e.g. ticket.revoked"
                onChange={(event) => {
                  setAction(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Actor user ID" htmlFor="audit-actor">
              <Input
                id="audit-actor"
                value={actorUserId}
                placeholder="Supabase UUID"
                onChange={(event) => {
                  setActorUserId(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Sort order" htmlFor="audit-sort">
              <Select
                id="audit-sort"
                value={sortOrder}
                onChange={(event) => {
                  setSortOrder(event.target.value as SortOrder);
                  setPage(1);
                }}
              >
                <option value="desc">Newest first</option>
                <option value="asc">Oldest first</option>
              </Select>
            </FormField>
            <FormField label="From" htmlFor="audit-from">
              <Input
                id="audit-from"
                type="datetime-local"
                value={fromDate}
                onChange={(event) => {
                  setFromDate(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="To" htmlFor="audit-to">
              <Input
                id="audit-to"
                type="datetime-local"
                value={toDate}
                onChange={(event) => {
                  setToDate(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
          </div>
          {filterError ? (
            <p className="text-xs text-destructive" role="alert">
              {filterError}
            </p>
          ) : null}
          <Button type="button" variant="outline" size="sm" onClick={resetFilters}>
            Clear filters
          </Button>
        </CardContent>
      </Card>

      {auditQuery.isPending ? (
        <ManagementTableSkeleton title="audit logs" rows={6} columns={4} />
      ) : auditQuery.isError ? (
        <ManagementErrorState
          error={auditQuery.error}
          onRetry={() => void auditQuery.refetch()}
        />
      ) : entries.length === 0 ? (
        <ManagementEmptyState
          icon={ScrollText}
          title="No audit entries found"
          description="No backend audit records match the selected event or filters."
        />
      ) : (
        <>
          <AuditLogTable entries={entries} />
          <ManagementPagination
            page={page}
            total={auditQuery.data?.total ?? 0}
            pageSize={PAGE_SIZE}
            isFetching={auditQuery.isFetching}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
