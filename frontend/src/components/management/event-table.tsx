"use client";

import Link from "next/link";
import { EventStatusBadge } from "@/components/events/event-status-badge";
import { ManagementTable } from "@/components/management/management-table";
import { Button } from "@/components/ui/button";
import type { EventRecord } from "@/lib/api/contracts";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export function EventTable({
  events,
  selectedEventSlug,
  onSelectEvent,
}: {
  events: EventRecord[];
  selectedEventSlug: string | null;
  onSelectEvent: (slug: string) => void;
}) {
  return (
    <ManagementTable
      label="Events"
      headers={["Event", "Status", "Starts", "Venue", "Actions"]}
    >
      {events.map((event) => {
        const selected = selectedEventSlug === event.slug;

        return (
          <tr key={event.slug} className={cn(selected && "bg-primary/5")}>
            <td className="px-4 py-3">
              <Link
                href={`/events/${encodeURIComponent(event.slug)}`}
                className="font-medium hover:underline"
              >
                {event.name}
              </Link>
              <p className="mt-0.5 font-mono text-xs text-muted-foreground">{event.slug}</p>
            </td>
            <td className="px-4 py-3">
              <EventStatusBadge status={event.status} />
            </td>
            <td className="px-4 py-3 text-muted-foreground">{formatDate(event.starts_at)}</td>
            <td className="px-4 py-3 text-muted-foreground">{event.venue ?? "—"}</td>
            <td className="px-4 py-3">
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link href={`/events/${encodeURIComponent(event.slug)}`}>View</Link>
                </Button>
                <Button
                  type="button"
                  variant={selected ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => onSelectEvent(event.slug)}
                >
                  {selected ? "Selected" : "Select event"}
                </Button>
              </div>
            </td>
          </tr>
        );
      })}
    </ManagementTable>
  );
}
