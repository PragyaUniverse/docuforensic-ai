import type { ReactNode } from "react";
import { AlertOctagon, Inbox, Loader2, RefreshCw } from "lucide-react";
import { Button } from "./button";
import { cn } from "@/lib/utils";

export function Loading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cn("flex items-center justify-center gap-2 p-8 text-ink-3", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span className="font-mono text-xs">{label}</span>
    </div>
  );
}

export function ErrorState({
  title = "This view could not load",
  error,
  onRetry,
  className,
}: {
  title?: string;
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className={cn("flex flex-col items-start gap-2 p-6", className)}>
      <div className="flex items-center gap-2 text-ink">
        <AlertOctagon className="size-4 text-man" aria-hidden />
        <span className="font-medium">{title}</span>
      </div>
      <p className="max-w-prose text-ink-2">{msg}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          <RefreshCw aria-hidden /> Try again
        </Button>
      )}
    </div>
  );
}

export function Empty({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 p-10 text-center", className)}>
      <Inbox className="size-5 text-ink-3" aria-hidden />
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="max-w-md text-ink-3">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
