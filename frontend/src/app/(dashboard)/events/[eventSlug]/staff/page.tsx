"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UsersRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { StaffCreateForm } from "@/components/management/staff-create-form";
import { StaffTable } from "@/components/management/staff-table";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Select } from "@/components/ui/select";
import type { StaffCreateRequest, StaffRole } from "@/lib/api/contracts";
import { managementKeys } from "@/lib/api/query-keys";
import { ApiError } from "@/lib/api/errors";
import { useEventSlugParam } from "@/lib/management/route-params";

const PAGE_SIZE = 25;

function finalAdminError(error: unknown): string | null {
  if (
    error instanceof ApiError &&
    error.status === 409 &&
    (error.code === "FINAL_ADMIN" || /final administrator/i.test(error.message))
  ) {
    return "The backend protects the final administrator. Promote another admin before changing this membership.";
  }
  return null;
}

export default function StaffPage() {
  const slug = useEventSlugParam();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [role, setRole] = useState<StaffRole | "">("");

  const params = {
    page,
    page_size: PAGE_SIZE,
    role: role || undefined,
  };

  const staffQuery = useQuery({
    queryKey: managementKeys.staff(slug, params),
    queryFn: ({ signal }) => api.staff.list(slug, params, signal),
    enabled: Boolean(slug),
  });

  async function invalidateStaff() {
    await queryClient.invalidateQueries({ queryKey: managementKeys.staffAll(slug) });
  }

  const createMutation = useMutation({
    mutationFn: (body: StaffCreateRequest) => api.staff.create(slug, body),
    onSuccess: async () => {
      await invalidateStaff();
      toast.success("Staff member added");
    },
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, nextRole }: { userId: string; nextRole: StaffRole }) =>
      api.staff.updateRole(slug, userId, { role: nextRole }),
    onSuccess: async () => {
      await invalidateStaff();
      toast.success("Staff role updated");
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => api.staff.remove(slug, userId),
    onSuccess: async () => {
      await invalidateStaff();
      toast.success("Staff member removed");
    },
  });

  const staff = staffQuery.data?.items ?? [];
  const total = staffQuery.data?.total ?? 0;
  const mutationError =
    createMutation.error ?? roleMutation.error ?? removeMutation.error;
  const finalAdminMessage = finalAdminError(mutationError);

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title="Staff access"
        description="Manage event-scoped memberships. Roles are read from backend staff records, never from JWT claims."
        backHref={`/events/${encodeURIComponent(slug)}`}
        backLabel="Event"
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          {finalAdminMessage ? (
            <ManagementErrorState error={new ApiError(409, "FINAL_ADMIN", finalAdminMessage)} />
          ) : mutationError ? (
            <ManagementErrorState error={mutationError} />
          ) : null}

          <div className="w-full sm:w-56">
            <Select
              aria-label="Filter staff by role"
              value={role}
              onChange={(event) => {
                setRole(event.target.value as StaffRole | "");
                setPage(1);
              }}
            >
              <option value="">All roles</option>
              <option value="admin">Admin</option>
              <option value="checkin">Check-in</option>
              <option value="viewer">Viewer</option>
            </Select>
          </div>

          {staffQuery.isPending ? (
            <ManagementTableSkeleton title="staff" rows={4} columns={4} />
          ) : staffQuery.isError ? (
            <ManagementErrorState
              error={staffQuery.error}
              onRetry={() => void staffQuery.refetch()}
            />
          ) : staff.length === 0 ? (
            <ManagementEmptyState
              icon={UsersRound}
              title="No staff members found"
              description="No staff memberships match the selected event or role."
            />
          ) : (
            <>
              <StaffTable
                staff={staff}
                onRoleChange={(userId, nextRole) =>
                  roleMutation.mutateAsync({ userId, nextRole })
                }
                onRemove={(userId) => removeMutation.mutateAsync(userId)}
              />
              <ManagementPagination
                page={page}
                total={total}
                pageSize={PAGE_SIZE}
                isFetching={staffQuery.isFetching}
                onPageChange={setPage}
              />
            </>
          )}
        </div>

        <StaffCreateForm
          onCreate={(body) => createMutation.mutateAsync(body)}
          isCreating={createMutation.isPending}
        />
      </div>
    </div>
  );
}
