"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { describeManagementError } from "@/lib/management/errors";

export function ManagementErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const info = describeManagementError(error);

  return (
    <Alert variant={info.title === "Access restricted" ? "warning" : "destructive"}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{info.title}</p>
          <AlertDescription className="mt-1">{info.description}</AlertDescription>
          {onRetry && info.retryable ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={onRetry}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Try again
            </Button>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}
