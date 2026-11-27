import { BarChart3 } from "lucide-react";
import type { ReactNode } from "react";
import { AnalyticsError } from "@/components/dashboard/analytics-error";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";

export function ChartFrame({
  title,
  description,
  children,
  footer,
  isLoading = false,
  error,
  onRetry,
  empty = false,
  emptyMessage,
}: {
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: boolean;
  emptyMessage: string;
}) {
  return (
    <Card className="flex min-h-[24rem] flex-col">
      <CardHeader className="pb-2">
        <CardTitle>{title}</CardTitle>
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        {error ? (
          <AnalyticsError error={error} onRetry={onRetry} />
        ) : isLoading ? (
          <Skeleton className="h-64 flex-1" />
        ) : empty ? (
          <EmptyState
            icon={BarChart3}
            title="No data to display"
            description={emptyMessage}
            className="flex-1 border-0 bg-transparent py-10"
          />
        ) : (
          <div className="h-64 flex-1 pt-2">{children}</div>
        )}

        {footer ? (
          <div className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
            {footer}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
