"use client";

import type { ReactNode } from "react";
import { EmailDeliveryStatusBadge } from "@/components/management/email-delivery-status-badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { EmailDeliveryRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

/** Uses only backend response fields; no provider payload or recipient email exists here. */
export function EmailDeliveryDetailsDialog({ delivery }: { delivery: EmailDeliveryRecord }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="link" size="sm" className="h-auto p-0">
          Details
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Email delivery details</DialogTitle>
          <DialogDescription>
            Outbox metadata only. The backend does not expose recipient email addresses, message
            bodies, or provider responses here.
          </DialogDescription>
        </DialogHeader>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field
            label="Delivery reference"
            value={<span className="font-mono text-xs">{delivery.delivery_reference}</span>}
          />
          <Field label="Status" value={<EmailDeliveryStatusBadge status={delivery.status} />} />
          <Field label="Purpose" value={delivery.purpose.replace("_", " ")} />
          <Field
            label="Registration"
            value={<span className="font-mono text-xs">{delivery.registration_reference || "—"}</span>}
          />
          <Field
            label="Ticket"
            value={<span className="font-mono text-xs">{delivery.ticket_reference}</span>}
          />
          <Field label="Attempts" value={delivery.attempts} />
          <Field label="Resend sequence" value={delivery.resend_sequence} />
          <Field label="Error code" value={delivery.error_code ?? "—"} />
          <Field label="Next attempt" value={formatDateTime(delivery.next_attempt_at)} />
          <Field label="Created" value={formatDateTime(delivery.created_at)} />
          <Field label="Sent" value={formatDateTime(delivery.sent_at)} />
        </dl>
      </DialogContent>
    </Dialog>
  );
}
