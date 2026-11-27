"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

type ErrorStateProps = {
  error: unknown;
  onRetry?: () => void;
  className?: string;
};

export function ErrorState({ error, onRetry, className }: ErrorStateProps) {
  const isForbidden = error instanceof ApiError && error.isForbidden;
  const title = isForbidden ? "Access restricted" : "Something went wrong";
  const description =
    error instanceof Error
      ? error.message
      : "The request could not be completed. Please try again.";

  return (
    <Alert variant={isForbidden ? "warning" : "destructive"} className={cn(className)}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{title}</p>
          <p className="mt-1 opacity-90">{description}</p>
          {onRetry ? (
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
