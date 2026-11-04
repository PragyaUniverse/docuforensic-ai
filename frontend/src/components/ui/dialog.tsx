import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;

export function DialogContent({
  title,
  description,
  className,
  children,
}: {
  title: string;
  description?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-black/70" />
      <D.Content
        aria-describedby={description ? undefined : undefined}
        className={cn(
          "fixed left-1/2 top-1/2 z-50 flex max-h-[92vh] w-[min(1180px,96vw)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-md border border-line-strong bg-panel",
          className,
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <D.Title className="display text-[15px]">{title}</D.Title>
          <D.Close aria-label="Close" className="rounded-sm p-1 text-ink-3 hover:bg-hover hover:text-ink">
            <X className="size-4" />
          </D.Close>
        </div>
        <D.Description className="sr-only">{description ?? title}</D.Description>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      </D.Content>
    </D.Portal>
  );
}
