"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame } from "@/components/dashboard/chart-frame";
import type { RegistrationAnalyticsResponse } from "@/lib/api/contracts";
import { formatChartCount, toBucketChartData } from "@/lib/analytics/chart-data";

const TOOLTIP_STYLE = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "0.5rem",
  color: "var(--popover-foreground)",
  fontSize: "0.75rem",
};

export function RegistrationTrendChart({
  data,
  isLoading = false,
  error,
  onRetry,
}: {
  data?: RegistrationAnalyticsResponse | null;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const chartData = toBucketChartData(data?.buckets);
  const granularity = data?.granularity ?? "—";
  const total = formatChartCount(data?.total_in_range);

  return (
    <ChartFrame
      title="Registration trend"
      description={`Backend granularity: ${granularity}. Sparse periods are not filled.`}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      empty={chartData.length === 0}
      emptyMessage="No registrations match the selected range."
      footer={`${total} registrations in range`}
    >
      <p className="sr-only">
        Registration trend: {total} registrations across {chartData.length} {granularity} buckets.
      </p>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
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
            formatter={(value) => [formatChartCount(value), "Registrations"]}
          />
          <Area
            type="linear"
            dataKey="count"
            name="Registrations"
            stroke="var(--primary)"
            fill="var(--primary)"
            fillOpacity={0.12}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
