import { cn, humanize } from "@/lib/utils";

function render(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "true" : "false";
  return JSON.stringify(v);
}

/** Measured values, exactly as recorded. */
export function DataList({ data, className }: { data: Record<string, unknown>; className?: string }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return null;
  return (
    <dl className={cn("grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[13px]", className)}>
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-3">{humanize(k)}</dt>
          <dd className="break-words text-ink">{render(v)}</dd>
        </div>
      ))}
    </dl>
  );
}
