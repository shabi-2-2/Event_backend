"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { ChartFrame } from "@/components/dashboard/chart-frame";
import type { EmailAnalyticsResponse, EmailDeliveryStatus } from "@/lib/api/contracts";
import { formatChartCount } from "@/lib/analytics/chart-data";

const TOOLTIP_STYLE = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "0.5rem",
  color: "var(--popover-foreground)",
  fontSize: "0.75rem",
};

const STATUS_META: Array<{ status: EmailDeliveryStatus; label: string; color: string }> = [
  { status: "pending", label: "Pending", color: "var(--warning)" },
  { status: "sent", label: "Sent", color: "var(--success)" },
  { status: "failed", label: "Failed", color: "var(--destructive)" },
  { status: "dead_letter", label: "Dead letter", color: "var(--muted-foreground)" },
];

export function EmailDeliveryChart({
  data,
  isLoading = false,
  error,
  onRetry,
}: {
  data?: EmailAnalyticsResponse | null;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const chartData = STATUS_META.flatMap(({ status, label, color }) => {
    const value = data?.status_counts?.[status];
    return typeof value === "number" ? [{ name: label, value, color }] : [];
  });
  const total = chartData.reduce((sum, item) => sum + item.value, 0);
  const summary = data?.attempt_summary;
  const average = formatChartCount(summary?.average_attempts);

  return (
    <ChartFrame
      title="Email delivery status"
      description="All-time delivery-job statuses reported by the backend."
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      empty={total === 0}
      emptyMessage="No email deliveries have been queued for this event."
      footer={`${formatChartCount(data?.total_deliveries)} deliveries · ${formatChartCount(summary?.total_attempts)} attempts · average ${average} · ${formatChartCount(summary?.retried_deliveries)} retried`}
    >
      <p className="sr-only">
        Email delivery status: {formatChartCount(data?.status_counts?.pending)} pending,{" "}
        {formatChartCount(data?.status_counts?.sent)} sent,{" "}
        {formatChartCount(data?.status_counts?.failed)} failed, and{" "}
        {formatChartCount(data?.status_counts?.dead_letter)} dead-letter deliveries.
      </p>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="name"
            innerRadius={55}
            outerRadius={85}
            paddingAngle={1}
            isAnimationActive={false}
          >
            {chartData.map((item) => (
              <Cell key={item.name} fill={item.color} stroke="var(--card)" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value, name) => [formatChartCount(value), String(name)]}
          />
          <Legend wrapperStyle={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }} />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
