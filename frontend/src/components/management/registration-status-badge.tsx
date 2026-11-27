import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { RegistrationStatus } from "@/lib/api/contracts";

const VARIANT: Record<RegistrationStatus, BadgeProps["variant"]> = {
  registered: "secondary",
  checked_in: "success",
  cancelled: "destructive",
};

export function RegistrationStatusBadge({ status }: { status: RegistrationStatus }) {
  return (
    <Badge variant={VARIANT[status]} className="capitalize">
      {status.replace("_", " ")}
    </Badge>
  );
}
