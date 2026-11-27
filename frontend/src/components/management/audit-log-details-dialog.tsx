"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { AuditLogRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

function ContextValue({ value }: { value: string | number | boolean | null }) {
  if (value === null) {
    return <span className="text-muted-foreground">—</span>;
  }

  if (typeof value === "string") {
    return <span className="break-words font-mono text-xs">{value || "—"}</span>;
  }

  return <span>{String(value)}</span>;
}

export function AuditLogDetailsDialog({ entry }: { entry: AuditLogRecord }) {
  const contextEntries = Object.entries(entry.context);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="link" size="sm" className="h-auto p-0">
          Details
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Audit entry</DialogTitle>
          <DialogDescription>
            Read-only record. Context values are limited to the backend-redacted metadata it
            returns; no before/after payloads or secrets are available.
          </DialogDescription>
        </DialogHeader>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field
            label="Reference"
            value={<span className="font-mono text-xs">{entry.audit_reference}</span>}
          />
          <Field label="Created" value={formatDateTime(entry.created_at)} />
          <Field label="Action" value={<span className="font-mono text-xs">{entry.action}</span>} />
          <Field label="Target type" value={entry.target_type} />
          <Field
            label="Target ID"
            value={<span className="font-mono text-xs">{entry.target_id ?? "—"}</span>}
          />
          <Field
            label="Actor"
            value={<span className="font-mono text-xs">{entry.actor_user_id ?? "System"}</span>}
          />
        </dl>
        <div className="mt-5 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Redacted context
          </p>
          {contextEntries.length === 0 ? (
            <p className="text-sm text-muted-foreground">No metadata recorded.</p>
          ) : (
            <dl className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2">
              {contextEntries.map(([key, value]) => (
                <div key={key} className="space-y-1">
                  <dt className="text-xs text-muted-foreground">{key}</dt>
                  <dd className="text-sm">
                    <ContextValue value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
