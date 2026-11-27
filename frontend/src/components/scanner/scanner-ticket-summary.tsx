import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ScannerTicketInfo } from "@/lib/api/contracts";

export function ScannerTicketSummary({ ticket }: { ticket: ScannerTicketInfo }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Verified attendee</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Attendee</dt>
            <dd className="mt-0.5 font-medium">{ticket.attendee_name}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">URN</dt>
            <dd className="mt-0.5 font-medium">{ticket.urn}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              Ticket status
            </dt>
            <dd className="mt-0.5 font-medium">{ticket.ticket_status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              Registration status
            </dt>
            <dd className="mt-0.5 font-medium">{ticket.registration_status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              Check-in status
            </dt>
            <dd className="mt-0.5 font-medium">{ticket.check_in_status}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
