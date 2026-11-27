"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { TicketRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

export function TicketDetailsDialog({ ticket }: { ticket: TicketRecord }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="link" size="sm" className="h-auto p-0">
          Details
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ticket details</DialogTitle>
          <DialogDescription>
            Backend-supported fields from the ticket list. No token, token hash, or QR payload is exposed.
          </DialogDescription>
        </DialogHeader>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Ticket reference" value={<span className="font-mono text-xs">{ticket.ticket_reference}</span>} />
          <Field label="Attendee" value={ticket.attendee_name} />
          <Field label="Attendee reference" value={<span className="font-mono text-xs">{ticket.attendee_reference || "—"}</span>} />
          <Field label="Registration status" value={ticket.registration_status.replace("_", " ")} />
          <Field label="Ticket status" value={ticket.ticket_status} />
          <Field label="Issued at" value={formatDateTime(ticket.issued_at)} />
          <Field label="Expires at" value={formatDateTime(ticket.expires_at)} />
          <Field label="Used at" value={formatDateTime(ticket.used_at)} />
          <Field label="Revoked at" value={formatDateTime(ticket.revoked_at)} />
          <Field label="Check-in time" value={formatDateTime(ticket.check_in_at)} />
        </dl>
      </DialogContent>
    </Dialog>
  );
}
