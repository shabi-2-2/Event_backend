import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function ManagementTableSkeleton({
  title,
  rows = 5,
  columns = 5,
}: {
  title?: string;
  rows?: number;
  columns?: number;
}) {
  return (
    <Card aria-busy="true" aria-label={title ? `Loading ${title}` : "Loading records"}>
      {title ? (
        <CardHeader>
          <Skeleton className="h-5 w-48" />
        </CardHeader>
      ) : null}
      <CardContent className="space-y-3">
        <Skeleton className="h-9 w-full" />
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div key={rowIndex} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: columns }).map((__, columnIndex) => (
              <Skeleton key={columnIndex} className="h-5 w-full" />
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
