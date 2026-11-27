import type * as React from "react";
import { cn } from "@/lib/utils";

export function AlertTitle({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return <div className={cn("font-medium", className)} {...props} />;
}

export function AlertDescription({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return <div className={cn("text-sm opacity-90", className)} {...props} />;
}

type AlertProps = React.ComponentProps<"div"> & {
  variant?: "default" | "destructive" | "warning";
};

export function Alert({ className, variant = "default", ...props }: AlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border px-4 py-3 text-sm",
        variant === "default" && "border-border bg-muted text-foreground",
        variant === "destructive" &&
          "border-destructive/30 bg-destructive/5 text-destructive",
        variant === "warning" && "border-warning/40 bg-warning/10 text-foreground",
        className,
      )}
      {...props}
    />
  );
}
