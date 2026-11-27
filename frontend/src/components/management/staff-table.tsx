"use client";

import { Trash2 } from "lucide-react";
import { ConfirmationDialog } from "@/components/management/confirmation-dialog";
import { ManagementTable } from "@/components/management/management-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { StaffRecord, StaffRole } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

export function StaffTable({
  staff,
  onRoleChange,
  onRemove,
}: {
  staff: StaffRecord[];
  onRoleChange: (userId: string, role: StaffRole) => void | Promise<unknown>;
  onRemove: (userId: string) => void | Promise<unknown>;
}) {
  return (
    <ManagementTable
      label="Staff members"
      headers={["User ID", "Role", "Added", "Actions"]}
    >
      {staff.map((member) => (
        <tr key={member.user_id}>
          <td className="px-4 py-3 font-mono text-xs">{member.user_id}</td>
          <td className="px-4 py-3">
            <Select
              aria-label={`Role for ${member.user_id}`}
              value={member.role}
              onChange={(event) => void onRoleChange(member.user_id, event.target.value as StaffRole)}
              className="h-9 max-w-40"
            >
              <option value="admin">Admin</option>
              <option value="checkin">Check-in</option>
              <option value="viewer">Viewer</option>
            </Select>
          </td>
          <td className="px-4 py-3 text-muted-foreground">{formatDateTime(member.created_at)}</td>
          <td className="px-4 py-3">
            <ConfirmationDialog
              destructive
              title="Remove this staff member?"
              description={`Access for ${member.user_id} will be removed from this event. The backend blocks removal of the final administrator.`}
              confirmLabel="Remove member"
              onConfirm={() => onRemove(member.user_id)}
              trigger={
                <Button type="button" variant="outline" size="sm">
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Remove
                </Button>
              }
            />
            {member.role === "admin" ? (
              <Badge variant="outline" className="ml-2">Admin</Badge>
            ) : null}
          </td>
        </tr>
      ))}
    </ManagementTable>
  );
}
