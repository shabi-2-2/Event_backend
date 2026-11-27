import type { AnalyticsDateRangeParams } from "@/lib/api/contracts";

export const DATE_RANGE_PRESETS = [
  { value: "all", label: "All time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "365d", label: "Last 12 months" },
  { value: "custom", label: "Custom range" },
] as const;

export type DateRangePreset = (typeof DATE_RANGE_PRESETS)[number]["value"];

export type DashboardDateRange = AnalyticsDateRangeParams & {
  key: string;
  label: string;
};

const MAX_RANGE_DAYS = 3_660;

function daysAgoIso(days: number, now: Date): string {
  const date = new Date(now);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString();
}

export function resolvePresetRange(
  preset: DateRangePreset,
  now: Date = new Date(),
): DashboardDateRange {
  if (preset === "all") {
    return { key: "all", label: "All time" };
  }

  const label = DATE_RANGE_PRESETS.find((option) => option.value === preset)?.label ?? preset;

  if (preset === "custom") {
    return { key: "custom", label };
  }

  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : preset === "90d" ? 90 : 365;

  return {
    key: preset,
    label,
    from_date: daysAgoIso(days, now),
    to_date: now.toISOString(),
  };
}

function localDate(input: string, endOfDay: boolean): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input)) {
    return null;
  }

  const [year, month, day] = input.split("-").map(Number);
  const date = new Date(
    year,
    month - 1,
    day,
    endOfDay ? 23 : 0,
    endOfDay ? 59 : 0,
    endOfDay ? 59 : 0,
    endOfDay ? 999 : 0,
  );

  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }

  return date;
}

export function resolveCustomRange(
  fromInput: string,
  toInput: string,
): { range?: DashboardDateRange; error?: string } {
  if (!fromInput || !toInput) {
    return { error: "Choose both a start and end date." };
  }

  const from = localDate(fromInput, false);
  const to = localDate(toInput, true);

  if (!from || !to) {
    return { error: "Enter valid calendar dates." };
  }

  if (to.getTime() < from.getTime()) {
    return { error: "End date must not be before start date." };
  }

  const spanDays = (to.getTime() - from.getTime()) / 86_400_000;
  if (spanDays > MAX_RANGE_DAYS) {
    return { error: "Date range cannot exceed 10 years." };
  }

  const fromIso = from.toISOString();
  const toIso = to.toISOString();

  return {
    range: {
      key: `${fromIso}_${toIso}`,
      label: "Custom range",
      from_date: fromIso,
      to_date: toIso,
    },
  };
}
