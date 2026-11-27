"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { EmailDeliveryTable } from "@/components/management/email-delivery-table";
import { ManagementEmptyState } from "@/components/management/management-empty-state";
import { ManagementErrorState } from "@/components/management/management-error-state";
import { ManagementPageHeader } from "@/components/management/management-page-header";
import { ManagementPagination } from "@/components/management/management-pagination";
import { ManagementTableSkeleton } from "@/components/management/management-table-skeleton";
import { useApiClient } from "@/components/providers/api-client-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  EmailDeliveryListParams,
  EmailDeliveryRecord,
  EmailDeliveryStatus,
} from "@/lib/api/contracts";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import { useEventSlugParam } from "@/lib/management/route-params";
import {
  datetimeLocalToUtc,
  parseAttemptFilter,
} from "@/lib/operations/filters";
import { parseEmailDeliveryPage } from "@/lib/operations/validation";

const PAGE_SIZE = 25;

export default function EmailDeliveriesPage() {
  const slug = useEventSlugParam();

  // Remount on event change so filters, in-flight retries, and page state are
  // never reused for a different event.
  return <EmailDeliveriesWorkspace key={slug} slug={slug} />;
}

function EmailDeliveriesWorkspace({ slug }: { slug: string }) {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<EmailDeliveryStatus | "">("");
  const [registrationReference, setRegistrationReference] = useState("");
  const [ticketReference, setTicketReference] = useState("");
  const [minAttempts, setMinAttempts] = useState("");
  const [maxAttempts, setMaxAttempts] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [nextAttemptBefore, setNextAttemptBefore] = useState("");
  const [nextAttemptAfter, setNextAttemptAfter] = useState("");
  const [retryingReference, setRetryingReference] = useState<string | null>(null);

  const retryAbortRef = useRef<AbortController | null>(null);
  const retryingRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      retryAbortRef.current?.abort();
      retryAbortRef.current = null;
      retryingRef.current = null;
    },
    [],
  );

  const parsedMinAttempts = parseAttemptFilter(minAttempts);
  const parsedMaxAttempts = parseAttemptFilter(maxAttempts);
  const beforeUtc = datetimeLocalToUtc(nextAttemptBefore);
  const afterUtc = datetimeLocalToUtc(nextAttemptAfter);
  const attemptsInvalid =
    (minAttempts.trim() !== "" && parsedMinAttempts === undefined) ||
    (maxAttempts.trim() !== "" && parsedMaxAttempts === undefined) ||
    (parsedMinAttempts !== undefined &&
      parsedMaxAttempts !== undefined &&
      parsedMaxAttempts < parsedMinAttempts);
  const datesInvalid =
    (nextAttemptBefore.trim() !== "" && beforeUtc === undefined) ||
    (nextAttemptAfter.trim() !== "" && afterUtc === undefined);
  const filterError = attemptsInvalid
    ? "Attempts must be whole numbers from 0 to 20, with minimum not above maximum."
    : datesInvalid
      ? "Enter valid dates and times for the next-attempt filters."
      : null;

  const params: EmailDeliveryListParams = {
    page,
    page_size: PAGE_SIZE,
    status: status || undefined,
    registration_reference: registrationReference.trim() || undefined,
    ticket_reference: ticketReference.trim() || undefined,
    min_attempts: attemptsInvalid ? undefined : parsedMinAttempts,
    max_attempts: attemptsInvalid ? undefined : parsedMaxAttempts,
    error_code: errorCode.trim() || undefined,
    next_attempt_before: datesInvalid ? undefined : beforeUtc,
    next_attempt_after: datesInvalid ? undefined : afterUtc,
  };

  const deliveriesQuery = useQuery({
    queryKey: managementKeys.emailDeliveries(slug, params),
    queryFn: async ({ signal }) => {
      const raw = await api.emailDeliveries.list(slug, params, signal);
      const parsed = parseEmailDeliveryPage(raw);
      if (!parsed) {
        throw new Error("The server returned an unexpected email delivery response.");
      }
      return parsed;
    },
    enabled: Boolean(slug),
  });

  const retryMutation = useMutation({
    mutationFn: (delivery: EmailDeliveryRecord) => {
      const controller = new AbortController();
      retryAbortRef.current = controller;
      return api.emailDeliveries.retry(
        slug,
        delivery.delivery_reference,
        controller.signal,
      );
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: managementKeys.emailDeliveriesAll(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.auditLogsAll(slug) }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.forEvent(slug) }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.emailDeliveries(slug) }),
      ]);
      toast.success("Delivery retry queued", {
        description: `${result.message} ${result.ticket_reference} · ${result.status}.`,
      });
    },
    onSettled: () => {
      retryAbortRef.current = null;
      retryingRef.current = null;
      setRetryingReference(null);
    },
  });

  async function handleRetry(delivery: EmailDeliveryRecord) {
    if (retryingRef.current || retryMutation.isPending) {
      return;
    }

    retryingRef.current = delivery.delivery_reference;
    setRetryingReference(delivery.delivery_reference);
    try {
      await retryMutation.mutateAsync(delivery);
    } catch {
      // Displayed by the page-level mutation error state.
    }
  }

  function resetFilters() {
    setPage(1);
    setStatus("");
    setRegistrationReference("");
    setTicketReference("");
    setMinAttempts("");
    setMaxAttempts("");
    setErrorCode("");
    setNextAttemptBefore("");
    setNextAttemptAfter("");
  }

  const deliveries = deliveriesQuery.data?.items ?? [];

  return (
    <div className="space-y-6">
      <ManagementPageHeader
        eyebrow={`Event · ${slug}`}
        title="Email operations"
        description="Monitor backend outbox jobs and retry failed or dead-letter deliveries. No email is sent from the browser."
        backHref={`/events/${encodeURIComponent(slug)}`}
        backLabel="Event"
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            Delivery filters
          </CardTitle>
          <CardDescription>
            Filters map directly to backend query parameters. Date-time filters are entered in
            your local time and sent as UTC.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <FormField label="Status" htmlFor="delivery-status">
              <Select
                id="delivery-status"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as EmailDeliveryStatus | "");
                  setPage(1);
                }}
              >
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="sent">Sent</option>
                <option value="failed">Failed</option>
                <option value="dead_letter">Dead letter</option>
              </Select>
            </FormField>
            <FormField label="Registration reference" htmlFor="delivery-registration">
              <Input
                id="delivery-registration"
                value={registrationReference}
                maxLength={64}
                placeholder="URN"
                onChange={(event) => {
                  setRegistrationReference(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Ticket reference" htmlFor="delivery-ticket">
              <Input
                id="delivery-ticket"
                value={ticketReference}
                maxLength={64}
                placeholder="Ticket reference"
                onChange={(event) => {
                  setTicketReference(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Minimum attempts" htmlFor="delivery-min-attempts">
              <Input
                id="delivery-min-attempts"
                type="number"
                min={0}
                max={20}
                value={minAttempts}
                onChange={(event) => {
                  setMinAttempts(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Maximum attempts" htmlFor="delivery-max-attempts">
              <Input
                id="delivery-max-attempts"
                type="number"
                min={0}
                max={20}
                value={maxAttempts}
                onChange={(event) => {
                  setMaxAttempts(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Error code" htmlFor="delivery-error-code">
              <Input
                id="delivery-error-code"
                value={errorCode}
                maxLength={64}
                placeholder="e.g. SMTP_TIMEOUT"
                onChange={(event) => {
                  setErrorCode(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Next attempt after" htmlFor="delivery-next-after">
              <Input
                id="delivery-next-after"
                type="datetime-local"
                value={nextAttemptAfter}
                onChange={(event) => {
                  setNextAttemptAfter(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
            <FormField label="Next attempt before" htmlFor="delivery-next-before">
              <Input
                id="delivery-next-before"
                type="datetime-local"
                value={nextAttemptBefore}
                onChange={(event) => {
                  setNextAttemptBefore(event.target.value);
                  setPage(1);
                }}
              />
            </FormField>
          </div>
          {filterError ? (
            <p className="text-xs text-destructive" role="alert">
              {filterError}
            </p>
          ) : null}
          <Button type="button" variant="outline" size="sm" onClick={resetFilters}>
            Clear filters
          </Button>
        </CardContent>
      </Card>

      {retryMutation.isError ? (
        <ManagementErrorState error={retryMutation.error} />
      ) : null}

      {deliveriesQuery.isPending ? (
        <ManagementTableSkeleton title="email deliveries" rows={6} columns={4} />
      ) : deliveriesQuery.isError ? (
        <ManagementErrorState
          error={deliveriesQuery.error}
          onRetry={() => void deliveriesQuery.refetch()}
        />
      ) : deliveries.length === 0 ? (
        <ManagementEmptyState
          icon={Mail}
          title="No email deliveries found"
          description="No outbox jobs match the selected event or filters."
        />
      ) : (
        <>
          <EmailDeliveryTable
            deliveries={deliveries}
            onRetry={(delivery) => void handleRetry(delivery)}
            retryDisabled={retryMutation.isPending}
            retryingReference={retryMutation.isPending ? retryingReference : null}
          />
          <ManagementPagination
            page={page}
            total={deliveriesQuery.data?.total ?? 0}
            pageSize={PAGE_SIZE}
            isFetching={deliveriesQuery.isFetching}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
