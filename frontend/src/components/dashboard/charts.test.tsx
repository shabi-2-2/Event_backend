import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AttendanceChart } from "@/components/dashboard/attendance-chart";
import { CheckinTrendChart } from "@/components/dashboard/checkin-trend-chart";
import { EmailDeliveryChart } from "@/components/dashboard/email-delivery-chart";
import { RegistrationTrendChart } from "@/components/dashboard/registration-trend-chart";

vi.mock("recharts", async () => await import("@/test/mocks/recharts"));

function chartData() {
  const chartRaw = screen
    .queryAllByTestId("chart")[0]
    ?.getAttribute("data-chart-data");
  if (chartRaw && chartRaw !== "[]") {
    return JSON.parse(chartRaw);
  }

  const seriesRaw = screen
    .queryAllByTestId("chart-series")[0]
    ?.getAttribute("data-series-data");

  return JSON.parse(seriesRaw ?? "[]");
}

describe("dashboard charts", () => {
  it("maps registration buckets to labeled, responsive chart data", () => {
    render(
      <RegistrationTrendChart
        data={{
          granularity: "day",
          from_date: null,
          to_date: null,
          buckets: [
            { period_start: "2026-01-15T12:00:00.000Z", period: "day", count: 7 },
          ],
          total_in_range: 7,
        }}
      />,
    );

    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    expect(chartData()).toEqual([{ label: "Jan 15, 2026", count: 7 }]);
    expect(screen.getByText("7 registrations in range")).toBeInTheDocument();
    expect(screen.getByTestId("chart-tooltip")).toBeInTheDocument();
  });

  it("maps attendance counts and displays the backend percentage", () => {
    render(
      <AttendanceChart
        data={{
          confirmed_registrations: 4,
          checked_in_attendees: 3,
          not_checked_in_attendees: 1,
          attendance_percentage: 75,
          buckets: [],
        }}
      />,
    );

    expect(chartData()).toEqual([
      { name: "Checked in", value: 3, color: "var(--success)" },
      { name: "Not checked in", value: 1, color: "var(--muted-foreground)" },
    ]);
    expect(screen.getByText(/Backend attendance percentage: 75%/)).toBeInTheDocument();
    expect(screen.getByTestId("chart-legend")).toBeInTheDocument();
  });

  it("maps check-in buckets and handles empty data", () => {
    const { rerender } = render(
      <CheckinTrendChart
        data={{
          confirmed_registrations: 10,
          checked_in_attendees: 2,
          not_checked_in_attendees: 8,
          attendance_percentage: 20,
          buckets: [
            { period_start: "2026-02-01T00:00:00.000Z", period: "month", count: 2 },
          ],
        }}
      />,
    );

    expect(chartData()).toEqual([{ label: "Feb 2026", count: 2 }]);

    rerender(
      <CheckinTrendChart
        data={{
          confirmed_registrations: 0,
          checked_in_attendees: 0,
          not_checked_in_attendees: 0,
          attendance_percentage: 0,
          buckets: [],
        }}
      />,
    );

    expect(screen.getByText("No data to display")).toBeInTheDocument();
    expect(screen.queryByTestId("chart")).not.toBeInTheDocument();
  });

  it("maps all four email statuses and handles missing counts", () => {
    const { rerender } = render(
      <EmailDeliveryChart
        data={{
          total_deliveries: 4,
          status_counts: { pending: 1, sent: 2, failed: 1, dead_letter: 0 },
          attempt_summary: {
            total_attempts: 9,
            max_attempts: 4,
            average_attempts: 2.25,
            retried_deliveries: 2,
          },
        }}
      />,
    );

    expect(chartData()).toEqual([
      { name: "Pending", value: 1, color: "var(--warning)" },
      { name: "Sent", value: 2, color: "var(--success)" },
      { name: "Failed", value: 1, color: "var(--destructive)" },
      { name: "Dead letter", value: 0, color: "var(--muted-foreground)" },
    ]);
    expect(screen.getByText(/average 2.25/)).toBeInTheDocument();

    rerender(<EmailDeliveryChart data={{ total_deliveries: 0 } as never} />);
    expect(screen.getByText("No data to display")).toBeInTheDocument();
  });
});
