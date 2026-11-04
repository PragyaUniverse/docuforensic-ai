import { ShieldAlert, ShieldCheck, ShieldQuestion, UserCheck, type LucideIcon } from "lucide-react";
import type { FindingStatus, ProcessingStatus, ReviewDecision, RiskLevel, Severity } from "@/api/types";
import { STATUS_META } from "@/lib/findings";
import { cn } from "@/lib/utils";

const plate = "inline-flex items-center gap-1.5 rounded-sm border font-mono font-medium uppercase tracking-[0.06em]";

export function StatusBadge({
  status,
  compact,
  className,
}: {
  status: FindingStatus;
  compact?: boolean;
  className?: string;
}) {
  const m = STATUS_META[status];
  const Icon = m.icon;
  return (
    <span
      title={m.meaning}
      className={cn(plate, "px-1.5 py-0.5 text-[10.5px]", m.text, m.bg, m.border, className)}
    >
      <Icon className="size-3" aria-hidden />
      {compact ? m.short : m.label}
      {compact && <span className="sr-only">{m.label}</span>}
    </span>
  );
}

const RISK: Record<RiskLevel, { label: string; icon: LucideIcon; cls: string }> = {
  high: { label: "High", icon: ShieldAlert, cls: "text-man border-man bg-man-dim" },
  medium: { label: "Medium", icon: ShieldQuestion, cls: "text-inc border-inc bg-inc-dim" },
  low: { label: "Low", icon: ShieldCheck, cls: "text-ok border-ok bg-ok-dim" },
  undetermined: { label: "Undetermined", icon: ShieldQuestion, cls: "text-ink-2 border-line-strong bg-raised" },
};

export function RiskPlate({ risk, assessed = true, large }: { risk: RiskLevel; assessed?: boolean; large?: boolean }) {
  const r = assessed ? RISK[risk] : { label: "Not assessed", icon: ShieldQuestion, cls: RISK.undetermined.cls };
  const Icon = r.icon;
  return (
    <span className={cn(plate, large ? "px-3 py-1.5 text-[13px]" : "px-2 py-1 text-[11px]", r.cls)}>
      <Icon className={large ? "size-4" : "size-3.5"} aria-hidden />
      Risk: {r.label}
    </span>
  );
}

export function HumanReviewPlate() {
  return (
    <span className={cn(plate, "border-line-strong bg-raised px-2 py-1 text-[11px] text-ink")}>
      <UserCheck className="size-3.5" aria-hidden />
      Requires human review
    </span>
  );
}

const PROC: Record<ProcessingStatus, { label: string; cls: string }> = {
  pending: { label: "Pending", cls: "text-ink-3 border-line" },
  processing: { label: "Processing", cls: "text-ink border-line-strong" },
  ok: { label: "OK", cls: "text-ok border-ok/60" },
  degraded: { label: "Degraded", cls: "text-inc border-inc/70" },
  unsupported: { label: "Unsupported", cls: "text-ink-2 border-line-strong bg-raised" },
  failed: { label: "Failed", cls: "text-man border-man/70" },
};

export function ProcBadge({ status }: { status: ProcessingStatus }) {
  const p = PROC[status] ?? PROC.pending;
  return <span className={cn(plate, "px-1.5 py-0.5 text-[10.5px]", p.cls)}>{p.label}</span>;
}

const REVIEW: Record<ReviewDecision, { label: string; cls: string }> = {
  pending: { label: "Awaiting review", cls: "text-ink-3 border-line" },
  confirmed: { label: "Reviewer confirmed", cls: "text-ink border-ink/70" },
  dismissed: { label: "Reviewer dismissed", cls: "text-ink-3 border-line-strong line-through decoration-ink-3" },
  escalated: { label: "Escalated", cls: "text-ink border-inc" },
};

export function ReviewBadge({ decision }: { decision: ReviewDecision }) {
  const r = REVIEW[decision];
  return <span className={cn(plate, "px-1.5 py-0.5 text-[10px]", r.cls)}>{r.label}</span>;
}

export function SeverityText({ severity }: { severity: Severity }) {
  return <span className="font-mono text-[11px] uppercase text-ink-2">Severity {severity}</span>;
}

export function ConfidenceMeter({ value, label = "Confidence", low }: { value: number; label?: string; low?: boolean }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <span className="inline-flex items-center gap-1.5" title={`${label}: ${Math.round(v * 100)}%`}>
      <span aria-hidden className="relative block h-[5px] w-12 overflow-hidden bg-line-strong">
        <span className={cn("absolute inset-y-0 left-0", low ? "bg-inc" : "bg-ink")} style={{ width: `${v * 100}%` }} />
      </span>
      <span className={cn("font-mono text-[11px]", low ? "text-inc" : "text-ink-2")}>
        {Math.round(v * 100)}%<span className="sr-only"> {label}</span>
      </span>
    </span>
  );
}
