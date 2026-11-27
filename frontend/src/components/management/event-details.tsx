import type { ReactNode } from "react";
import { EventStatusBadge } from "@/components/events/event-status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EventRecord } from "@/lib/api/contracts";
import { getRegistrationWindowStatus } from "@/lib/analytics/registration-window";
import { formatDateTime } from "@/lib/format";

function Field({
  label,
  value,
  className = "",
}: {
  label: string;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className={`space-y-1 ${className}`}>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">{value}</dd>
    </div>
  );
}

export function EventDetails({ event }: { event: EventRecord }) {
  const registration = getRegistrationWindowStatus(event);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Configuration
          <EventStatusBadge status={event.status} />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Slug" value={<span className="font-mono text-xs">{event.slug}</span>} />
          <Field label="Name" value={event.name} />
          <Field label="Time zone" value={event.timezone} />
          <Field label="Starts at" value={formatDateTime(event.starts_at)} />
          <Field label="Ends at" value={formatDateTime(event.ends_at)} />
          <Field label="Venue" value={event.venue ?? "Not set"} />
          <Field label="Capacity" value={event.capacity?.toLocaleString() ?? "No limit"} />
          <Field label="Registration status" value={`${registration.label} — ${registration.detail}`} />
          <Field label="Created at" value={formatDateTime(event.created_at)} />
          <Field label="Updated at" value={formatDateTime(event.updated_at)} />
          <Field label="Description" value={event.description ?? "No description"} className="sm:col-span-2 lg:col-span-3" />
        </dl>
      </CardContent>
    </Card>
  );
}
