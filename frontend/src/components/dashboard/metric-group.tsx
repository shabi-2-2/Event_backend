import { MetricCard } from "@/components/dashboard/metric-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MetricGroupDescriptor } from "@/lib/analytics/metrics";

export function MetricGroup({ group }: { group: MetricGroupDescriptor }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>{group.title}</CardTitle>
        <p className="text-xs text-muted-foreground">{group.description}</p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {group.metrics.map((metric) => (
            <MetricCard key={metric.key} metric={metric} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
