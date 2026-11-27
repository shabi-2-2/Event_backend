import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { EmailDeliveryStatus } from "@/lib/api/contracts";

const VARIANT: Record<EmailDeliveryStatus, BadgeProps["variant"]> = {
  pending: "warning",
  sent: "success",
  failed: "destructive",
  dead_letter: "destructive",
};

const LABEL: Record<EmailDeliveryStatus, string> = {
  pending: "Pending",
  sent: "Sent",
  failed: "Failed",
  dead_letter: "Dead letter",
};

export function EmailDeliveryStatusBadge({ status }: { status: EmailDeliveryStatus }) {
  return <Badge variant={VARIANT[status]}>{LABEL[status]}</Badge>;
}
