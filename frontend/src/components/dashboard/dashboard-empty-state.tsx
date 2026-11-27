"use client";

import { CalendarDays } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { EventRecord } from "@/lib/api/contracts";

export function DashboardEmptyState({
  events,
  eventsLoading,
  onSelectEvent,
}: {
  events: EventRecord[];
  eventsLoading: boolean;
  onSelectEvent: (slug: string) => void;
}) {
  if (eventsLoading) {
    return (
      <EmptyState
        icon={CalendarDays}
        title="Loading events"
        description="Checking which events are available to your account."
      />
    );
  }

  if (events.length === 0) {
    return (
      <EmptyState
        icon={CalendarDays}
        title="No events available"
        description="No accessible events were returned. An administrator must create and assign an event before analytics can be displayed."
        action={
          <Button asChild variant="outline">
            <Link href="/events">View event list</Link>
          </Button>
        }
      />
    );
  }

  return (
    <EmptyState
      icon={CalendarDays}
      title="Select an event"
      description="Choose one of your accessible events to load its dashboard. No event is selected automatically."
      action={
        <div className="w-full max-w-xs space-y-2 text-left">
          <Label htmlFor="empty-event-select">Event</Label>
          <Select
            id="empty-event-select"
            defaultValue=""
            onChange={(event) => {
              if (event.target.value) {
                onSelectEvent(event.target.value);
              }
            }}
          >
            <option value="">Choose an event…</option>
            {events.map((event) => (
              <option key={event.slug} value={event.slug}>
                {event.name}
              </option>
            ))}
          </Select>
        </div>
      }
    />
  );
}
