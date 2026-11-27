"use client";

import { AlertTriangle, RotateCcw, Ban } from "lucide-react";
import { ConfirmationDialog } from "@/components/management/confirmation-dialog";
import { ManagementTable } from "@/components/management/management-table";
import { RegistrationStatusBadge } from "@/components/management/registration-status-badge";
import { TicketDetailsDialog } from "@/components/management/ticket-details-dialog";
import { TicketStatusBadge } from "@/components/management/ticket-status-badge";
import { Button } from "@/components/ui/button";
import type { TicketRecord } from "@/lib/api/contracts";
import { formatDate } from "@/lib/format";

export function TicketTable({
  tickets,
  onRevoke,
  onResend,
}: {
  tickets: TicketRecord[];
  onRevoke: (ticket: TicketRecord) => void | Promise<unknown>;
  onResend: (ticket: TicketRecord) => void | Promise<unknown>;
}) {
  return (
    <ManagementTable
      label="Tickets"
      headers={["Ticket", "Attendee", "Registration", "Status", "Issued", "Actions"]}
    >
      {tickets.map((ticket) => {
        const canRevoke = ticket.ticket_status === "active" && !ticket.check_in_at;
        const canResend =
          ticket.ticket_status === "active" &&
          ticket.registration_status !== "cancelled";

        return (
          <tr key={ticket.ticket_reference}>
            <td className="px-4 py-3 font-mono text-xs">{ticket.ticket_reference}</td>
            <td className="px-4 py-3 font-medium">{ticket.attendee_name}</td>
            <td className="px-4 py-3">
              <RegistrationStatusBadge status={ticket.registration_status} />
            </td>
            <td className="px-4 py-3">
              <TicketStatusBadge status={ticket.ticket_status} />
            </td>
            <td className="px-4 py-3 text-muted-foreground">{formatDate(ticket.issued_at)}</td>
            <td className="px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <TicketDetailsDialog ticket={ticket} />
                <ConfirmationDialog
                  destructive
                  title="Revoke this ticket?"
                  description={`Ticket ${ticket.ticket_reference} will become revoked. This action is recorded in the audit log.`}
                  confirmLabel="Revoke ticket"
                  confirmDisabled={!canRevoke}
                  onConfirm={() => onRevoke(ticket)}
                  trigger={
                    <Button type="button" variant="outline" size="sm" disabled={!canRevoke}>
                      <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                      Revoke
                    </Button>
                  }
                />
                <ConfirmationDialog
                  title="Resend this ticket email?"
                  description={`A new delivery job will be queued for ticket ${ticket.ticket_reference}. The ticket itself is not reissued.`}
                  confirmLabel="Queue resend"
                  confirmDisabled={!canResend}
                  onConfirm={() => onResend(ticket)}
                  trigger={
                    <Button type="button" variant="outline" size="sm" disabled={!canResend}>
                      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                      Resend
                    </Button>
                  }
                />
                {!canRevoke && !canResend ? (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                    Immutable
                  </span>
                ) : null}
              </div>
            </td>
          </tr>
        );
      })}
    </ManagementTable>
  );
}
