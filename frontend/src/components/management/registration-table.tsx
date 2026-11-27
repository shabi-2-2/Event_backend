"use client";

import Link from "next/link";
import { CheckinStatusBadge } from "@/components/management/checkin-status-badge";
import { ManagementTable } from "@/components/management/management-table";
import { RegistrationStatusBadge } from "@/components/management/registration-status-badge";
import { TicketStatusBadge } from "@/components/management/ticket-status-badge";
import type { RegistrationRecord } from "@/lib/api/contracts";
import { formatDate } from "@/lib/format";

export function RegistrationTable({
  eventSlug,
  registrations,
}: {
  eventSlug: string;
  registrations: RegistrationRecord[];
}) {
  return (
    <ManagementTable
      label="Registrations"
      headers={["Reference", "Attendee", "Email", "Status", "Ticket", "Check-in", "Registered", "Actions"]}
    >
      {registrations.map((registration) => (
        <tr key={registration.registration_reference}>
          <td className="px-4 py-3 font-mono text-xs">{registration.registration_reference || "—"}</td>
          <td className="px-4 py-3 font-medium">{registration.attendee_name}</td>
          <td className="px-4 py-3 text-muted-foreground">{registration.email}</td>
          <td className="px-4 py-3">
            <RegistrationStatusBadge status={registration.registration_status} />
          </td>
          <td className="px-4 py-3">
            {registration.ticket_status ? (
              <TicketStatusBadge status={registration.ticket_status} />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </td>
          <td className="px-4 py-3">
            <CheckinStatusBadge status={registration.check_in_status} />
          </td>
          <td className="px-4 py-3 text-muted-foreground">{formatDate(registration.registered_at)}</td>
          <td className="px-4 py-3">
            <Link
              href={`/events/${encodeURIComponent(eventSlug)}/registrations/${encodeURIComponent(registration.registration_reference)}`}
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
