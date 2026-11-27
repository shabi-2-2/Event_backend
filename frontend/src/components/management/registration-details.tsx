import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckinStatusBadge } from "@/components/management/checkin-status-badge";
import { RegistrationStatusBadge } from "@/components/management/registration-status-badge";
import { TicketStatusBadge } from "@/components/management/ticket-status-badge";
import type { RegistrationRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">{value}</dd>
    </div>
  );
}

export function RegistrationDetails({
  registration,
}: {
  registration: RegistrationRecord;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{registration.attendee_name}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Registration reference" value={<span className="font-mono text-xs">{registration.registration_reference || "—"}</span>} />
          <Field label="Attendee reference" value={<span className="font-mono text-xs">{registration.attendee_reference || "—"}</span>} />
          <Field label="Status" value={<RegistrationStatusBadge status={registration.registration_status} />} />
          <Field label="Email" value={registration.email} />
          <Field label="Phone" value={registration.phone ?? "Not provided"} />
          <Field label="Registered at" value={formatDateTime(registration.registered_at)} />
          <Field label="Checked in at" value={formatDateTime(registration.checked_in_at)} />
          <Field label="Cancelled at" value={formatDateTime(registration.cancelled_at)} />
          <Field label="Ticket reference" value={<span className="font-mono text-xs">{registration.ticket_reference ?? "—"}</span>} />
          <Field label="Ticket status" value={registration.ticket_status ? <TicketStatusBadge status={registration.ticket_status} /> : "—"} />
          <Field label="Check-in status" value={<CheckinStatusBadge status={registration.check_in_status} />} />
          <Field label="Check-in time" value={formatDateTime(registration.check_in_at)} />
          <Field label="Station" value={registration.station ?? "—"} />
        </dl>
      </CardContent>
    </Card>
  );
}
