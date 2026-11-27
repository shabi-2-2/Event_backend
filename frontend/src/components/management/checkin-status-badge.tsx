import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { CheckinFilterStatus } from "@/lib/api/contracts";

const VARIANT: Record<CheckinFilterStatus, BadgeProps["variant"]> = {
  pending: "warning",
  checked_in: "success",
};

export function CheckinStatusBadge({ status }: { status: CheckinFilterStatus }) {
  return (
    <Badge variant={VARIANT[status]} className="capitalize">
      {status.replace("_", " ")}
    </Badge>
  );
}
