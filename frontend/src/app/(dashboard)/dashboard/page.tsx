"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AnalyticsError } from "@/components/dashboard/analytics-error";
import { AttendanceChart } from "@/components/dashboard/attendance-chart";
import { CheckinTrendChart } from "@/components/dashboard/checkin-trend-chart";
import { DashboardEmptyState } from "@/components/dashboard/dashboard-empty-state";
import { DashboardHeader } from "@/components/dashboard/dashboard-header";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { EmailDeliveryChart } from "@/components/dashboard/email-delivery-chart";
import { MetricGroup } from "@/components/dashboard/metric-group";
import { RegistrationTrendChart } from "@/components/dashboard/registration-trend-chart";
import { useEventSelection } from "@/components/layout/event-selection-context";
import { useApiClient } from "@/components/providers/api-client-provider";
import {
  resolveCustomRange,
  resolvePresetRange,
  type DateRangePreset,
} from "@/lib/analytics/date-range";
import { buildMetricGroups } from "@/lib/analytics/metrics";
import { dashboardKeys } from "@/lib/api/query-keys";

const EVENT_PAGE_SIZE = 100;
const ANALYTICS_STALE_TIME = 60_000;

export default function DashboardPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const { selectedEventSlug, selectEvent } = useEventSelection();
  const slug = selectedEventSlug ?? "";
  const [anchor] = useState(() => new Date());
  const [preset, setPreset] = useState<DateRangePreset>("all");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  const customResult = useMemo(
    () => resolveCustomRange(customFrom, customTo),
    [customFrom, customTo],
  );
  const range = useMemo(
    () =>
      preset === "custom"
        ? (customResult.range ?? { key: "custom-invalid", label: "Custom range" })
        : resolvePresetRange(preset, anchor),
    [anchor, customResult.range, preset],
  );
  const rangeReady = preset !== "custom" || Boolean(customResult.range);

  const eventsQuery = useQuery({
    queryKey: dashboardKeys.events(),
    queryFn: ({ signal }) => api.events.list({ page: 1, page_size: EVENT_PAGE_SIZE }, signal),
    staleTime: ANALYTICS_STALE_TIME,
  });

  const eventQuery = useQuery({
    queryKey: dashboardKeys.event(slug),
    queryFn: ({ signal }) => api.events.get(slug, signal),
    enabled: Boolean(slug),
    staleTime: ANALYTICS_STALE_TIME,
  });

  const overviewQuery = useQuery({
    queryKey: dashboardKeys.overview(slug),
    queryFn: ({ signal }) => api.analytics.overview(slug, signal),
    enabled: Boolean(slug),
    staleTime: ANALYTICS_STALE_TIME,
  });

  const emailQuery = useQuery({
    queryKey: dashboardKeys.emailDeliveries(slug),
    queryFn: ({ signal }) => api.analytics.emailDeliveries(slug, signal),
    enabled: Boolean(slug),
    staleTime: ANALYTICS_STALE_TIME,
  });

  const registrationsQuery = useQuery({
    queryKey: dashboardKeys.registrations(slug, range.key),
    queryFn: ({ signal }) =>
      api.analytics.registrations(
        slug,
        { from_date: range.from_date, to_date: range.to_date },
        signal,
      ),
    enabled: Boolean(slug) && rangeReady,
    staleTime: ANALYTICS_STALE_TIME,
  });

  const attendanceQuery = useQuery({
    queryKey: dashboardKeys.attendance(slug, range.key),
    queryFn: ({ signal }) =>
      api.analytics.attendance(
        slug,
        { from_date: range.from_date, to_date: range.to_date },
        signal,
      ),
    enabled: Boolean(slug) && rangeReady,
    staleTime: ANALYTICS_STALE_TIME,
  });

  const isInitialLoading =
    Boolean(slug) &&
    (eventQuery.isPending ||
      overviewQuery.isPending ||
      emailQuery.isPending ||
      (rangeReady && (registrationsQuery.isPending || attendanceQuery.isPending)));
  const isRefreshing = [
    eventsQuery,
    eventQuery,
    overviewQuery,
    emailQuery,
    registrationsQuery,
    attendanceQuery,
  ].some((query) => query.isFetching && !query.isPending);

  const events = eventsQuery.data?.items ?? [];
  const metricGroups = buildMetricGroups(overviewQuery.data, attendanceQuery.data);

  const handleRefresh = () => {
    void queryClient.invalidateQueries({ queryKey: dashboardKeys.all });
  };

  return (
    <div className="space-y-6">
      <DashboardHeader
        event={eventQuery.data}
        events={events}
        eventsLoading={eventsQuery.isPending}
        preset={preset}
        fromInput={customFrom}
        toInput={customTo}
        rangeError={customResult.error}
        isRefreshing={isRefreshing}
        onSelectEvent={selectEvent}
        onPresetChange={setPreset}
        onFromChange={setCustomFrom}
        onToChange={setCustomTo}
        onRefresh={handleRefresh}
      />

      {!selectedEventSlug ? (
        <DashboardEmptyState
          events={events}
          eventsLoading={eventsQuery.isPending}
          onSelectEvent={selectEvent}
        />
      ) : isInitialLoading ? (
        <DashboardSkeleton />
      ) : (
        <>
          {eventsQuery.error ? (
            <AnalyticsError error={eventsQuery.error} onRetry={handleRefresh} />
          ) : null}
          {eventQuery.error ? (
            <AnalyticsError error={eventQuery.error} onRetry={handleRefresh} />
          ) : null}

          {overviewQuery.error || attendanceQuery.data || overviewQuery.data ? (
            <div className="space-y-4">
              {overviewQuery.error ? (
                <AnalyticsError
                  error={overviewQuery.error}
                  onRetry={() => void overviewQuery.refetch()}
                />
              ) : null}
              {metricGroups.map((group) => (
                <MetricGroup key={group.key} group={group} />
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-2">
            <RegistrationTrendChart
              data={registrationsQuery.data}
              isLoading={registrationsQuery.isPending}
              error={registrationsQuery.error}
              onRetry={() => void registrationsQuery.refetch()}
            />
            <AttendanceChart
              data={attendanceQuery.data}
              isLoading={attendanceQuery.isPending}
              error={attendanceQuery.error}
              onRetry={() => void attendanceQuery.refetch()}
            />
            <CheckinTrendChart
              data={attendanceQuery.data}
              isLoading={attendanceQuery.isPending}
              error={attendanceQuery.error}
              onRetry={() => void attendanceQuery.refetch()}
            />
            <EmailDeliveryChart
              data={emailQuery.data}
              isLoading={emailQuery.isPending}
              error={emailQuery.error}
              onRetry={() => void emailQuery.refetch()}
            />
          </div>
        </>
      )}
    </div>
  );
}
