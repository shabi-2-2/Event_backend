"use client";

import Link from "next/link";
import { CheckinStatusBadge } from "@/components/management/checkin-status-badge";
import { ManagementTable } from "@/components/management/management-table";
import { RegistrationStatusBadge } from "@/components/management/registration-status-badge";
import { TicketStatusBadge } from "@/components/management/ticket-status-badge";
import type { AttendeeRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

export function AttendeeTable({
  eventSlug,
  attendees,
}: {
  eventSlug: string;
  attendees: AttendeeRecord[];
}) {
  return (
    <ManagementTable
      label="Attendees"
      headers={["Attendee", "URN", "Registration", "Ticket", "Check-in", "Checked in at", "Actions"]}
    >
      {attendees.map((attendee) => (
        <tr key={attendee.attendee_reference}>
          <td className="px-4 py-3 font-medium">{attendee.full_name}</td>
          <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{attendee.urn || "—"}</td>
          <td className="px-4 py-3">
            <RegistrationStatusBadge status={attendee.registration_status} />
          </td>
          <td className="px-4 py-3">
            {attendee.ticket_status ? (
              <TicketStatusBadge status={attendee.ticket_status} />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </td>
          <td className="px-4 py-3">
            <CheckinStatusBadge status={attendee.check_in_status} />
          </td>
          <td className="px-4 py-3 text-muted-foreground">
            {formatDateTime(attendee.checked_in_at)}
          </td>
          <td className="px-4 py-3">
            <Link
              href={`/events/${encodeURIComponent(eventSlug)}/attendees/${encodeURIComponent(attendee.attendee_reference)}`}
              className="text-sm font-medium text-primary hover:underline"
            >
              Details
            </Link>
          </td>
        </tr>
      ))}
    </ManagementTable>
  );
}
