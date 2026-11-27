"use client";

import { CalendarDays, MapPin, RefreshCw } from "lucide-react";
import { DateRangeSelector } from "@/components/dashboard/date-range-selector";
import { EventStatusBadge } from "@/components/events/event-status-badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { EventRecord } from "@/lib/api/contracts";
import type { DateRangePreset } from "@/lib/analytics/date-range";
import { getRegistrationWindowStatus } from "@/lib/analytics/registration-window";
import { formatDateTime } from "@/lib/format";

export function DashboardHeader({
  event,
  events,
  eventsLoading,
  preset,
  fromInput,
  toInput,
  rangeError,
  isRefreshing,
  onSelectEvent,
  onPresetChange,
  onFromChange,
  onToChange,
  onRefresh,
}: {
  event?: EventRecord | null;
  events: EventRecord[];
  eventsLoading: boolean;
  preset: DateRangePreset;
  fromInput: string;
  toInput: string;
  rangeError?: string;
  isRefreshing: boolean;
  onSelectEvent: (slug: string | null) => void;
  onPresetChange: (preset: DateRangePreset) => void;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  onRefresh: () => void;
}) {
  const registration = event ? getRegistrationWindowStatus(event) : null;

  return (
    <section className="space-y-5" aria-labelledby="dashboard-heading">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
              Event dashboard
            </p>
            {event ? <EventStatusBadge status={event.status} /> : null}
          </div>
          <h1 id="dashboard-heading" className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {event?.name ?? "Event analytics"}
          </h1>
          {event ? (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <CalendarDays className="h-4 w-4" aria-hidden="true" />
                {formatDateTime(event.starts_at)}
              </span>
              <span className="flex items-center gap-1.5">
                <MapPin className="h-4 w-4" aria-hidden="true" />
                {event.venue ?? "Venue not set"}
              </span>
              {registration ? (
                <span
                  className={
                    registration.tone === "success"
                      ? "text-success"
                      : registration.tone === "warning"
                        ? "text-warning"
                        : undefined
                  }
                  title={registration.detail}
                >
                  Registration: {registration.label}
                </span>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Choose an event to load its analytics.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end xl:items-start">
          <div className="w-full space-y-2 sm:w-60">
            <Label htmlFor="dashboard-event">Event</Label>
            <Select
              id="dashboard-event"
              value={event?.slug ?? ""}
              disabled={eventsLoading}
              onChange={(eventChange) => onSelectEvent(eventChange.target.value || null)}
            >
              <option value="">Select an event</option>
              {events.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </Select>
          </div>

          <DateRangeSelector
            preset={preset}
            fromInput={fromInput}
            toInput={toInput}
            error={rangeError}
            onPresetChange={onPresetChange}
            onFromChange={onFromChange}
            onToChange={onToChange}
          />

          <Button
            type="button"
            variant="outline"
            size="icon"
            className="shrink-0"
            disabled={!event || isRefreshing}
            onClick={onRefresh}
            aria-label="Refresh dashboard data"
            title="Refresh dashboard data"
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
          </Button>
        </div>
      </div>

      {event?.registration_opens_at || event?.registration_closes_at ? (
        <p className="text-xs text-muted-foreground">
          Registration window: {registration?.detail}
        </p>
      ) : null}
    </section>
  );
}
