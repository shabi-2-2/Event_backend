"use client";

import { RotateCcw } from "lucide-react";
import { ConfirmationDialog } from "@/components/management/confirmation-dialog";
import { EmailDeliveryDetailsDialog } from "@/components/management/email-delivery-details-dialog";
import { EmailDeliveryStatusBadge } from "@/components/management/email-delivery-status-badge";
import { ManagementTable } from "@/components/management/management-table";
import { Button } from "@/components/ui/button";
import type { EmailDeliveryRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

export function EmailDeliveryTable({
  deliveries,
  onRetry,
  retryDisabled,
  retryingReference,
}: {
  deliveries: EmailDeliveryRecord[];
  onRetry: (delivery: EmailDeliveryRecord) => void;
  retryDisabled: boolean;
  retryingReference: string | null;
}) {
  return (
    <ManagementTable
      label="Email deliveries"
      headers={[
        "Delivery",
        "Purpose",
        "Registration",
        "Ticket",
        "Status",
        "Attempts",
        "Created",
        "Actions",
      ]}
    >
      {deliveries.map((delivery) => {
        const retryable = delivery.status === "failed" || delivery.status === "dead_letter";
        const rowBusy = retryingReference === delivery.delivery_reference;

        return (
          <tr key={delivery.delivery_reference}>
            <td className="px-4 py-3 font-mono text-xs">{delivery.delivery_reference}</td>
            <td className="px-4 py-3 capitalize">{delivery.purpose.replace("_", " ")}</td>
            <td className="px-4 py-3 font-mono text-xs">
              {delivery.registration_reference || "—"}
            </td>
            <td className="px-4 py-3 font-mono text-xs">{delivery.ticket_reference}</td>
            <td className="px-4 py-3">
              <EmailDeliveryStatusBadge status={delivery.status} />
            </td>
            <td className="px-4 py-3">{delivery.attempts}</td>
            <td className="px-4 py-3 text-muted-foreground">
              {formatDateTime(delivery.created_at)}
            </td>
            <td className="px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <EmailDeliveryDetailsDialog delivery={delivery} />
                {retryable ? (
                  <ConfirmationDialog
                    title="Retry this delivery?"
                    description="The backend queues a replacement job and keeps the original delivery history. Only one active job per ticket is allowed."
                    confirmLabel="Queue retry"
                    confirmDisabled={retryDisabled}
                    onConfirm={() => onRetry(delivery)}
                    trigger={
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={retryDisabled}
                        aria-label={`Retry delivery ${delivery.delivery_reference}`}
                      >
                        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                        {rowBusy ? "Retrying…" : "Retry"}
                      </Button>
                    }
                  />
                ) : (
                  <span className="text-xs text-muted-foreground">No retry available</span>
                )}
              </div>
            </td>
          </tr>
        );
      })}
    </ManagementTable>
  );
}
