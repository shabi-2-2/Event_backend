import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { TicketStatus } from "@/lib/api/contracts";

const VARIANT: Record<TicketStatus, BadgeProps["variant"]> = {
  active: "success",
  used: "secondary",
  revoked: "destructive",
  expired: "warning",
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return (
    <Badge variant={VARIANT[status]} className="capitalize">
      {status}
    </Badge>
  );
}
