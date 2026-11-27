import { Info } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatMetric, type MetricDescriptor } from "@/lib/analytics/metrics";

const TONE_CLASS: Record<NonNullable<MetricDescriptor["tone"]>, string> = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
};

export function MetricCard({ metric }: { metric: MetricDescriptor }) {
  const Icon = metric.icon;

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="truncate text-xs font-medium text-muted-foreground">{metric.label}</p>
            <span
              className="inline-flex items-center text-muted-foreground/70"
              title={metric.description}
              aria-label={metric.description}
            >
              <Info className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="sr-only">{metric.description}</span>
            </span>
          </div>
          <p
            className={cn(
              "mt-2 text-2xl font-semibold tracking-tight tabular-nums",
              TONE_CLASS[metric.tone ?? "default"],
            )}
          >
            {formatMetric(metric)}
          </p>
        </div>
        {Icon ? (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
        ) : null}
      </div>
    </Card>
  );
}
