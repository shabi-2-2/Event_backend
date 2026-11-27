import { describe, expect, it } from "vitest";
import type { EventRecord } from "@/lib/api/contracts";
import { bucketLabel, formatChartCount, toBucketChartData } from "@/lib/analytics/chart-data";
import {
  resolveCustomRange,
  resolvePresetRange,
} from "@/lib/analytics/date-range";
import { buildMetricGroups, formatMetric } from "@/lib/analytics/metrics";
import { getRegistrationWindowStatus } from "@/lib/analytics/registration-window";

const fixedNow = new Date("2026-06-15T12:00:00.000Z");

describe("date range helpers", () => {
  it("omits date parameters for all time presets", () => {
    const range = resolvePresetRange("all", fixedNow);
    expect(range).toMatchObject({ key: "all", label: "All time" });
    expect(range.from_date).toBeUndefined();
    expect(range.to_date).toBeUndefined();
  });

  it("produces timezone-aware ISO parameters for presets", () => {
    const range = resolvePresetRange("30d", fixedNow);
    expect(range.from_date).toBe("2026-05-16T12:00:00.000Z");
    expect(range.to_date).toBe("2026-06-15T12:00:00.000Z");
  });

  it("validates custom ranges", () => {
    const valid = resolveCustomRange("2026-06-01", "2026-06-30");
    expect(valid.range?.from_date).toBe("2026-06-01T00:00:00.000Z");
    expect(valid.range?.to_date).toBe("2026-06-30T23:59:59.999Z");

    expect(resolveCustomRange("2026-06-30", "2026-06-01").error).toMatch(/before/);
    expect(resolveCustomRange("2026-01-01", "2037-01-01").error).toMatch(/10 years/);
    expect(resolveCustomRange("", "2026-06-30").error).toMatch(/both/);
  });
});

describe("chart data mapping", () => {
  it("formats bucket labels using backend granularity", () => {
    expect(
      bucketLabel({
        period_start: "2026-01-15T12:00:00.000Z",
        period: "day",
        count: 2,
      }),
    ).toBe("Jan 15, 2026");
    expect(
      bucketLabel({
        period_start: "2026-01-15T12:00:00.000Z",
        period: "week",
        count: 2,
      }),
    ).toBe("Week of Jan 15, 2026");
    expect(
      bucketLabel({
        period_start: "2026-01-15T12:00:00.000Z",
        period: "month",
        count: 2,
      }),
    ).toBe("Jan 2026");
  });

  it("maps sparse buckets without filling empty periods", () => {
    const data = toBucketChartData([
      { period_start: "2026-01-15T12:00:00.000Z", period: "day", count: 3 },
    ]);

    expect(data).toEqual([{ label: "Jan 15, 2026", count: 3 }]);
    expect(toBucketChartData([])).toEqual([]);
    expect(formatChartCount(undefined)).toBe("—");
  });
});

describe("metric definitions", () => {
  it("uses backend fields and renders unavailable metrics as an em dash", () => {
    const groups = buildMetricGroups(
      {
        total_registrations: 10,
        confirmed_registrations: 8,
        cancelled_registrations: 2,
        declined_rsvps: 1,
        checked_in_attendees: 4,
        not_checked_in_attendees: 4,
        active_tickets: 3,
        used_tickets: 4,
        revoked_tickets: 1,
        expired_tickets: 0,
        pending_email_deliveries: 2,
        sent_email_deliveries: 5,
        failed_email_deliveries: 1,
        dead_letter_email_deliveries: 0,
      },
      {
        confirmed_registrations: 8,
        checked_in_attendees: 4,
        not_checked_in_attendees: 4,
        attendance_percentage: 50,
        buckets: [],
      },
    );

    expect(groups).toHaveLength(4);
    const attendance = groups.find((group) => group.key === "attendance");
    const percentage = attendance?.metrics.find(
      (metric) => metric.key === "attendance_percentage",
    );

    expect(percentage?.value).toBe(50);
    expect(formatMetric(percentage!)).toBe("50%");
    expect(percentage?.description).toMatch(/non-cancelled registrations/);

    const partialGroups = buildMetricGroups(undefined, undefined);
    const total = partialGroups[0].metrics[0];
    expect(formatMetric(total)).toBe("—");
  });
});

describe("registration window display", () => {
  const event = {
    registration_opens_at: "2026-06-01T00:00:00.000Z",
    registration_closes_at: "2026-06-30T00:00:00.000Z",
  } as EventRecord;

  it("derives a display status from backend timestamps", () => {
    expect(getRegistrationWindowStatus(event, fixedNow)).toMatchObject({
      label: "Open",
      tone: "success",
    });
    expect(
      getRegistrationWindowStatus(
        event,
        new Date("2026-07-01T00:00:00.000Z"),
      ).label,
    ).toBe("Closed");
    expect(
      getRegistrationWindowStatus(
        { ...event, registration_opens_at: null, registration_closes_at: null } as EventRecord,
        fixedNow,
      ).label,
    ).toBe("Not configured");
  });
});
