import type { TimeBucket } from "@/lib/api/contracts";
import { formatDate } from "@/lib/format";

const monthYearFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  year: "numeric",
});

export function bucketLabel(bucket: TimeBucket): string {
  if (bucket.period === "month") {
    return monthYearFormatter.format(new Date(bucket.period_start));
  }

  if (bucket.period === "week") {
    return `Week of ${formatDate(bucket.period_start)}`;
  }

  return formatDate(bucket.period_start);
}

export function toBucketChartData(buckets: TimeBucket[] | undefined | null) {
  return (buckets ?? []).map((bucket) => ({
    label: bucketLabel(bucket),
    count: bucket.count,
  }));
}

export function formatChartCount(value: unknown): string {
  return typeof value === "number" ? value.toLocaleString() : "—";
}
