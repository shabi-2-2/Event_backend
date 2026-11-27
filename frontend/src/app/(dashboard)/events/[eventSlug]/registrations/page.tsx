"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { useState } from "react";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { RegistrationTable } from "@/components/management/registration-table";
import { useApiClient } from "@/components/providers/api-client-provider";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  CheckinFilterStatus,
  RegistrationStatus,
  TicketStatus,
} from "@/lib/api/contracts";
import { managementKeys } from "@/lib/api/query-keys";
import { useEventSlugParam } from "@/lib/management/route-params";

const PAGE_SIZE = 25;

export default function RegistrationsPage() {
  const slug = useEventSlugParam();
  const api = useApiClient();
  const [page, setPage] = useState(1);
  const [reference, setReference] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [registrationStatus, setRegistrationStatus] = useState<RegistrationStatus | "">(
    "",
  );
  const [ticketStatus, setTicketStatus] = useState<TicketStatus | "">("");
  const [checkinStatus, setCheckinStatus] = useState<CheckinFilterStatus | "">("");

  const params = {
    page,
    page_size: PAGE_SIZE,
    reference: reference || undefined,
    name: name || undefined,
    email: email || undefined,
    registration_status: registrationStatus || undefined,
    ticket_status: ticketStatus || undefined,
    check_in_status: checkinStatus || undefined,
  };

  const registrationsQuery = useQuery({
    queryKey: managementKeys.registrations(slug, params),
    queryFn: ({ signal }) => api.registrations.list(slug, params, signal),
    enabled: Boolean(slug),
  });

  const registrations = registrationsQuery.data?.items ?? [];
  const total = registrationsQuery.data?.total ?? 0;

  const updateFilter = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title="Registrations"
        description="Review registrations and cancellations. Declined RSVPs are tracked separately and do not appear here."
        backHref={`/events/${encodeURIComponent(slug)}`}
        backLabel="Event"
      />

      <div className="grid gap-4 rounded-xl border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-3">
        <FormField label="Reference" htmlFor="registration-reference">
          <Input
            id="registration-reference"
            value={reference}
            maxLength={100}
            placeholder="Partial reference"
            onChange={(event) => updateFilter(setReference)(event.target.value)}
          />
        </FormField>
        <FormField label="Attendee name" htmlFor="registration-name">
          <Input
            id="registration-name"
            value={name}
            maxLength={200}
            onChange={(event) => updateFilter(setName)(event.target.value)}
          />
        </FormField>
        <FormField label="Email" htmlFor="registration-email">
          <Input
            id="registration-email"
            type="email"
            value={email}
            maxLength={255}
            onChange={(event) => updateFilter(setEmail)(event.target.value)}
          />
        </FormField>
        <FormField label="Registration status" htmlFor="registration-status">
          <Select
            id="registration-status"
            value={registrationStatus}
            onChange={(event) =>
              updateFilter((value) =>
                setRegistrationStatus(value as RegistrationStatus | ""),
              )(event.target.value)
            }
          >
            <option value="">All statuses</option>
            <option value="registered">Registered</option>
            <option value="checked_in">Checked in</option>
            <option value="cancelled">Cancelled</option>
          </Select>
        </FormField>
        <FormField label="Ticket status" htmlFor="registration-ticket-status">
          <Select
            id="registration-ticket-status"
            value={ticketStatus}
            onChange={(event) =>
              updateFilter((value) =>
                setTicketStatus(value as TicketStatus | ""),
              )(event.target.value)
            }
          >
            <option value="">All ticket statuses</option>
            <option value="active">Active</option>
            <option value="used">Used</option>
            <option value="revoked">Revoked</option>
            <option value="expired">Expired</option>
          </Select>
        </FormField>
        <FormField label="Check-in status" htmlFor="registration-checkin-status">
          <Select
            id="registration-checkin-status"
            value={checkinStatus}
            onChange={(event) =>
              updateFilter((value) =>
                setCheckinStatus(value as CheckinFilterStatus | ""),
              )(event.target.value)
            }
          >
            <option value="">All check-in states</option>
            <option value="pending">Pending</option>
            <option value="checked_in">Checked in</option>
          </Select>
        </FormField>
      </div>

      {registrationsQuery.isPending ? (
        <ManagementTableSkeleton title="registrations" />
      ) : registrationsQuery.isError ? (
        <ManagementErrorState
          error={registrationsQuery.error}
          onRetry={() => void registrationsQuery.refetch()}
        />
      ) : registrations.length === 0 ? (
        <ManagementEmptyState
          icon={ClipboardList}
          title="No registrations found"
          description="No registration records match the selected event or filters."
        />
      ) : (
        <>
          <RegistrationTable eventSlug={slug} registrations={registrations} />
          <ManagementPagination
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            isFetching={registrationsQuery.isFetching}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
