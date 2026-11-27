"use client";

import { AuditLogDetailsDialog } from "@/components/management/audit-log-details-dialog";
import { ManagementTable } from "@/components/management/management-table";
import type { AuditLogRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

export function AuditLogTable({ entries }: { entries: AuditLogRecord[] }) {
  return (
    <ManagementTable
      label="Audit logs"
      headers={["When", "Action", "Actor", "Target", "Metadata", "Details"]}
    >
      {entries.map((entry) => (
        <tr key={entry.audit_reference}>
          <td className="px-4 py-3 text-muted-foreground">{formatDateTime(entry.created_at)}</td>
          <td className="px-4 py-3 font-mono text-xs">{entry.action}</td>
          <td className="px-4 py-3 font-mono text-xs">{entry.actor_user_id ?? "System"}</td>
          <td className="px-4 py-3">
            <span>{entry.target_type}</span>
            {entry.target_id ? (
              <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                {entry.target_id}
              </span>
            ) : null}
          </td>
          <td className="px-4 py-3">{Object.keys(entry.context).length} field(s)</td>
          <td className="px-4 py-3">
            <AuditLogDetailsDialog entry={entry} />
          </td>
        </tr>
      ))}
    </ManagementTable>
  );
}
