import type { ReactNode } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AttendeeRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";
import {
  isAdminAttendee,
  RESTRICTED_ATTENDEE_FIELDS,
} from "@/lib/management/attendees";
import { CheckinStatusBadge } from "@/components/management/checkin-status-badge";
import { RegistrationStatusBadge } from "@/components/management/registration-status-badge";
import { TicketStatusBadge } from "@/components/management/ticket-status-badge";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

export function AttendeeDetails({ attendee }: { attendee: AttendeeRecord }) {
  const admin = isAdminAttendee(attendee);

  return (
    <div className="space-y-4">
      {!admin ? (
        <Alert variant="warning">
          <AlertDescription>
            Your authorization level exposes only a restricted attendee view. The following
            fields are withheld by the backend: {RESTRICTED_ATTENDEE_FIELDS.join(", ")}.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{attendee.full_name}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Attendee reference" value={<span className="font-mono text-xs">{attendee.attendee_reference || "—"}</span>} />
            <Field label="URN" value={<span className="font-mono text-xs">{attendee.urn || "—"}</span>} />
            <Field label="Registration status" value={<RegistrationStatusBadge status={attendee.registration_status} />} />
            <Field label="Ticket status" value={attendee.ticket_status ? <TicketStatusBadge status={attendee.ticket_status} /> : "—"} />
            <Field label="Check-in status" value={<CheckinStatusBadge status={attendee.check_in_status} />} />
            <Field label="Checked in at" value={formatDateTime(attendee.checked_in_at)} />

            {admin ? (
              <>
                <Field label="Email" value={attendee.email} />
                <Field label="Phone" value={attendee.phone ?? "Not provided"} />
                <Field label="Registration reference" value={<span className="font-mono text-xs">{attendee.registration_reference || "—"}</span>} />
                <Field label="Registered at" value={formatDateTime(attendee.registered_at)} />
                <Field label="Cancelled at" value={formatDateTime(attendee.cancelled_at)} />
                <Field label="Ticket reference" value={<span className="font-mono text-xs">{attendee.ticket_reference ?? "—"}</span>} />
                <Field label="Ticket expires at" value={formatDateTime(attendee.ticket_expires_at)} />
                <Field label="Ticket used at" value={formatDateTime(attendee.ticket_used_at)} />
                <Field label="Check-in time" value={formatDateTime(attendee.check_in_at)} />
                <Field label="Station" value={attendee.station ?? "—"} />
              </>
            ) : null}
          </dl>
          {admin ? (
            <p className="mt-5 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">Admin view</Badge>
              Ticket credentials and QR payloads are never returned by the backend.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
