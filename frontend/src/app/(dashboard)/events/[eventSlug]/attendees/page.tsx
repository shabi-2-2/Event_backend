"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, Users } from "lucide-react";
import { useState } from "react";
import { AttendeeTable } from "@/components/management/attendee-table";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  AttendeeSortField,
  CheckinFilterStatus,
  RegistrationStatus,
  SortOrder,
  TicketStatus,
} from "@/lib/api/contracts";
import { managementKeys } from "@/lib/api/query-keys";
import { hasAdminAttendeeData } from "@/lib/management/attendees";
import { useEventSlugParam } from "@/lib/management/route-params";

const PAGE_SIZE = 25;

export default function AttendeesPage() {
  const slug = useEventSlugParam();
  const api = useApiClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [urn, setUrn] = useState("");
  const [email, setEmail] = useState("");
  const [registrationStatus, setRegistrationStatus] = useState<RegistrationStatus | "">("");
  const [ticketStatus, setTicketStatus] = useState<TicketStatus | "">("");
  const [checkinStatus, setCheckinStatus] = useState<CheckinFilterStatus | "">("");
  const [sortBy, setSortBy] = useState<AttendeeSortField>("registered_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  const params = {
    page,
    page_size: PAGE_SIZE,
    search: appliedSearch || undefined,
    urn: urn || undefined,
    email: email || undefined,
    registration_status: registrationStatus || undefined,
    ticket_status: ticketStatus || undefined,
    check_in_status: checkinStatus || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  };

  const attendeesQuery = useQuery({
    queryKey: managementKeys.attendees(slug, params),
    queryFn: ({ signal }) => api.attendees.list(slug, params, signal),
    enabled: Boolean(slug),
  });

  const attendees = attendeesQuery.data?.items ?? [];
  const total = attendeesQuery.data?.total ?? 0;
  const adminData = hasAdminAttendeeData(attendees);

  const applyFilters = () => {
    setPage(1);
    setAppliedSearch(search.trim());
  };

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title="Attendees"
        description="Search attendee records. Contact details appear only in the authorized detail view."
        backHref="/dashboard"
        backLabel="Dashboard"
      />

      <div className="grid gap-4 rounded-xl border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-4">
        <FormField label="Search name or URN" htmlFor="attendee-search">
          <div className="flex gap-2">
            <Input
              id="attendee-search"
              value={search}
              maxLength={200}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") applyFilters();
              }}
            />
            <Button type="button" variant="outline" size="icon" aria-label="Apply search" onClick={applyFilters}>
              <Search className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </FormField>
        <FormField label="URN" htmlFor="attendee-urn">
          <Input
            id="attendee-urn"
            value={urn}
            maxLength={64}
            onChange={(event) => {
              setUrn(event.target.value);
              setPage(1);
            }}
          />
        </FormField>
        {adminData ? (
          <FormField label="Email" htmlFor="attendee-email" hint="Administrators only.">
            <Input
              id="attendee-email"
              value={email}
              maxLength={255}
              onChange={(event) => {
                setEmail(event.target.value);
                setPage(1);
              }}
            />
          </FormField>
        ) : null}
        <FormField label="Registration status" htmlFor="attendee-registration-status">
          <Select
            id="attendee-registration-status"
            value={registrationStatus}
            onChange={(event) => {
              setRegistrationStatus(event.target.value as RegistrationStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            <option value="registered">Registered</option>
            <option value="checked_in">Checked in</option>
            <option value="cancelled">Cancelled</option>
          </Select>
        </FormField>
        <FormField label="Ticket status" htmlFor="attendee-ticket-status">
          <Select
            id="attendee-ticket-status"
            value={ticketStatus}
            onChange={(event) => {
              setTicketStatus(event.target.value as TicketStatus | "");
              setPage(1);
            }}
          >
            <option value="">All ticket statuses</option>
            <option value="active">Active</option>
            <option value="used">Used</option>
            <option value="revoked">Revoked</option>
            <option value="expired">Expired</option>
          </Select>
        </FormField>
        <FormField label="Check-in status" htmlFor="attendee-checkin-status">
          <Select
            id="attendee-checkin-status"
            value={checkinStatus}
            onChange={(event) => {
              setCheckinStatus(event.target.value as CheckinFilterStatus | "");
              setPage(1);
            }}
          >
            <option value="">All check-in states</option>
            <option value="pending">Pending</option>
            <option value="checked_in">Checked in</option>
          </Select>
        </FormField>
        <FormField label="Sort by" htmlFor="attendee-sort-by">
          <Select
            id="attendee-sort-by"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value as AttendeeSortField)}
          >
            <option value="registered_at">Registered at</option>
            <option value="name">Name</option>
          </Select>
        </FormField>
        <FormField label="Sort order" htmlFor="attendee-sort-order">
          <Select
            id="attendee-sort-order"
            value={sortOrder}
            onChange={(event) => setSortOrder(event.target.value as SortOrder)}
          >
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </Select>
        </FormField>
      </div>

      {attendeesQuery.isPending ? (
        <ManagementTableSkeleton title="attendees" />
      ) : attendeesQuery.isError ? (
        <ManagementErrorState
          error={attendeesQuery.error}
          onRetry={() => void attendeesQuery.refetch()}
        />
      ) : attendees.length === 0 ? (
        <ManagementEmptyState
          icon={Users}
          title="No attendees found"
          description="No attendee records match the selected event or filters."
        />
      ) : (
        <>
          <AttendeeTable eventSlug={slug} attendees={attendees} />
          <ManagementPagination
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            isFetching={attendeesQuery.isFetching}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
