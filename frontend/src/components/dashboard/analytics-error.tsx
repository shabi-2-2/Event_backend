"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import type { ValidationIssue } from "@/lib/api/contracts";

function validationSummary(details?: ValidationIssue[]): string | null {
  const messages = details
    ?.map((detail) => (typeof detail.msg === "string" ? detail.msg : null))
    .filter((message): message is string => Boolean(message));

  return messages?.length ? messages.join(" ") : null;
}

export function AnalyticsError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const apiError = error instanceof ApiError ? error : null;
  let title = "Could not load analytics";
  let description =
    error instanceof Error ? error.message : "The request could not be completed.";

  if (apiError?.isUnauthorized) {
    title = "Authentication required";
    description = "Your session is no longer valid. Sign in again to view analytics.";
  } else if (apiError?.isForbidden) {
    title = "Access restricted";
    description = "You do not have analytics access for this event.";
  } else if (apiError?.isValidationError) {
    title = "Invalid date range";
    description = validationSummary(apiError.details) ?? apiError.message;
  } else if (apiError?.isRateLimited) {
    title = "Too many requests";
    description = apiError.retryAfterSeconds
      ? `Please retry in ${apiError.retryAfterSeconds} seconds.`
      : apiError.message;
  }

  return (
    <Alert variant={apiError?.isForbidden ? "warning" : "destructive"}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription className="mt-1">{description}</AlertDescription>
          {onRetry ? (
            <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Try again
            </Button>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}
