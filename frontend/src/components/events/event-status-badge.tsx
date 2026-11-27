import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { EventStatus } from "@/lib/api/contracts";

const STATUS_VARIANT: Record<EventStatus, BadgeProps["variant"]> = {
  draft: "secondary",
  published: "success",
  archived: "outline",
  cancelled: "destructive",
};

export function EventStatusBadge({ status }: { status: EventStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status]} className="capitalize">
      {status}
    </Badge>
  );
}
