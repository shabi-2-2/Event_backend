import type { ReactNode } from "react";

type ChartProps = {
  data?: unknown[];
  children?: ReactNode;
};

function ChartStub({ data, children }: ChartProps) {
  return (
    <div data-testid="chart" data-chart-data={JSON.stringify(data ?? [])}>
      {children}
    </div>
  );
}

function SeriesStub({
  data,
  dataKey,
  name,
  fill,
  stroke,
}: {
  data?: unknown[];
  dataKey?: string;
  name?: string;
  fill?: string;
  stroke?: string;
}) {
  return (
    <div
      data-testid="chart-series"
      data-series-data={JSON.stringify(data ?? [])}
      data-data-key={dataKey}
      data-name={name}
      data-fill={fill}
      data-stroke={stroke}
    />
  );
}

export function ResponsiveContainer({ children }: { children: ReactNode }) {
  return <div data-testid="responsive-container">{children}</div>;
}

export const AreaChart = ChartStub;
export const BarChart = ChartStub;
export const PieChart = ChartStub;
export const Area = SeriesStub;
export const Bar = SeriesStub;
export const Pie = SeriesStub;

export function Cell({ fill }: { fill?: string }) {
  return <div data-testid="chart-cell" data-fill={fill} />;
}

export function CartesianGrid() {
  return <div data-testid="chart-grid" />;
}

export function XAxis({ dataKey }: { dataKey?: string }) {
  return <div data-testid="chart-x-axis" data-data-key={dataKey} />;
}

export function YAxis() {
  return <div data-testid="chart-y-axis" />;
}

export function Tooltip() {
  return <div data-testid="chart-tooltip" />;
}

export function Legend() {
  return <div data-testid="chart-legend" />;
}
