"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { ChartFrame } from "@/components/dashboard/chart-frame";
import type { AttendanceAnalyticsResponse } from "@/lib/api/contracts";
import { formatChartCount } from "@/lib/analytics/chart-data";

const TOOLTIP_STYLE = {
  backgroundColor: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "0.5rem",
  color: "var(--popover-foreground)",
  fontSize: "0.75rem",
};

export function AttendanceChart({
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
  const checkedIn = data?.checked_in_attendees;
  const notCheckedIn = data?.not_checked_in_attendees;
  const hasCounts = typeof checkedIn === "number" && typeof notCheckedIn === "number";
  const chartData = hasCounts
    ? [
        { name: "Checked in", value: checkedIn, color: "var(--success)" },
        { name: "Not checked in", value: notCheckedIn, color: "var(--muted-foreground)" },
      ]
    : [];
  const total = chartData.reduce((sum, item) => sum + (item.value ?? 0), 0);
  const percentage =
    typeof data?.attendance_percentage === "number"
      ? `${data.attendance_percentage.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
      : "—";

  return (
    <ChartFrame
      title="Attendance overview"
      description="Checked-in versus not-yet-checked-in confirmed registrations."
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      empty={!hasCounts || total === 0}
      emptyMessage="No confirmed registrations are available for this event."
      footer={`Backend attendance percentage: ${percentage}`}
    >
      <p className="sr-only">
        Attendance overview: {formatChartCount(checkedIn)} checked in and{" "}
        {formatChartCount(notCheckedIn)} not checked in. Backend attendance percentage {percentage}.
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
