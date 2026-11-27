"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame } from "@/components/dashboard/chart-frame";
import type { AttendanceAnalyticsResponse } from "@/lib/api/contracts";
import { formatChartCount, toBucketChartData } from "@/lib/analytics/chart-data";

const TOOLTIP_STYLE = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "0.5rem",
  color: "var(--popover-foreground)",
  fontSize: "0.75rem",
};

export function CheckinTrendChart({
  data,
  isLoading = false,
  error,
  onRetry,
}: {
  data?: AttendanceAnalyticsResponse | null;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const chartData = toBucketChartData(data?.buckets);
  const total = chartData.reduce((sum, item) => sum + item.count, 0);

  return (
    <ChartFrame
      title="Check-in trend"
      description="Check-in rows grouped by the backend's selected granularity."
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      empty={chartData.length === 0}
      emptyMessage="No check-ins were recorded in the selected range."
      footer="Buckets count check-in rows within the range; headline totals are all-time."
    >
      <p className="sr-only">
        Check-in trend: {formatChartCount(total)} check-ins across {chartData.length} buckets.
      </p>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            interval="preserveStartEnd"
          />
          <YAxis
            allowDecimals={false}
            width={48}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value) => [formatChartCount(value), "Check-ins"]}
          />
          <Bar
            dataKey="count"
            name="Check-ins"
            fill="var(--primary)"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
