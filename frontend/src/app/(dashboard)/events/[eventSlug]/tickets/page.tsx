"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ticket } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { TicketTable } from "@/components/management/ticket-table";
import { useApiClient } from "@/components/providers/api-client-provider";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { TicketRecord, TicketStatus } from "@/lib/api/contracts";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import { useEventSlugParam } from "@/lib/management/route-params";

const PAGE_SIZE = 25;

export default function TicketsPage() {
  const slug = useEventSlugParam();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [reference, setReference] = useState("");
  const [ticketStatus, setTicketStatus] = useState<TicketStatus | "">("");

  const params = {
    page,
    page_size: PAGE_SIZE,
    reference: reference || undefined,
    ticket_status: ticketStatus || undefined,
  };

  const ticketsQuery = useQuery({
    queryKey: managementKeys.tickets(slug, params),
    queryFn: ({ signal }) => api.tickets.list(slug, params, signal),
    enabled: Boolean(slug),
  });

  async function invalidateTicketData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: managementKeys.ticketsAll(slug) }),
      queryClient.invalidateQueries({ queryKey: managementKeys.attendeesAll(slug) }),
      queryClient.invalidateQueries({ queryKey: managementKeys.registrationsAll(slug) }),
      queryClient.invalidateQueries({ queryKey: managementKeys.event(slug) }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
  }

  const revokeMutation = useMutation({
    mutationFn: (ticket: TicketRecord) =>
      api.tickets.revoke(slug, ticket.ticket_reference),
    onSuccess: async (_result, ticket) => {
      await invalidateTicketData();
      toast.success("Ticket revoked", {
        description: `${ticket.ticket_reference} is now revoked.`,
      });
    },
  });

  const resendMutation = useMutation({
    mutationFn: (ticket: TicketRecord) =>
      api.tickets.resend(slug, ticket.ticket_reference),
    onSuccess: async (result) => {
      await invalidateTicketData();
      toast.success("Ticket email queued", {
        description: `${result.ticket_reference} · delivery ${result.delivery_reference} (${result.status}).`,
      });
    },
  });

  const tickets = ticketsQuery.data?.items ?? [];
  const total = ticketsQuery.data?.total ?? 0;
  const mutationError = revokeMutation.error ?? resendMutation.error;

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title="Tickets"
        description="Review ticket state and use backend-supported revocation and email resend operations. Tokens and QR payloads are never displayed."
        backHref={`/events/${encodeURIComponent(slug)}`}
        backLabel="Event"
      />

      <div className="grid gap-4 rounded-xl border border-border bg-card p-4 sm:grid-cols-2">
        <FormField label="Ticket reference" htmlFor="ticket-reference">
          <Input
            id="ticket-reference"
            value={reference}
            maxLength={100}
            placeholder="Partial reference"
            onChange={(event) => {
              setReference(event.target.value);
              setPage(1);
            }}
          />
        </FormField>
        <FormField label="Status" htmlFor="ticket-status">
          <Select
            id="ticket-status"
            value={ticketStatus}
            onChange={(event) => {
              setTicketStatus(event.target.value as TicketStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="used">Used</option>
            <option value="revoked">Revoked</option>
            <option value="expired">Expired</option>
          </Select>
        </FormField>
      </div>

      {mutationError ? <ManagementErrorState error={mutationError} /> : null}

      {ticketsQuery.isPending ? (
        <ManagementTableSkeleton title="tickets" />
      ) : ticketsQuery.isError ? (
        <ManagementErrorState
          error={ticketsQuery.error}
          onRetry={() => void ticketsQuery.refetch()}
        />
      ) : tickets.length === 0 ? (
        <ManagementEmptyState
          icon={Ticket}
          title="No tickets found"
          description="No ticket records match the selected event or filters."
        />
      ) : (
        <>
          <TicketTable
            tickets={tickets}
            onRevoke={(ticket) => revokeMutation.mutateAsync(ticket)}
            onResend={(ticket) => resendMutation.mutateAsync(ticket)}
          />
          <ManagementPagination
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            isFetching={ticketsQuery.isFetching}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
