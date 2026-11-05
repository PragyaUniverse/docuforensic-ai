import type { FindingStatus, ProcessingStatus, ReviewDecision, RiskLevel, Severity } from "@/api/types";
import { STATUS_META } from "@/lib/findings";
import { cn } from "@/lib/utils";

function Dot({ className }: { className: string }) {
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", className)} />;
}

const DOT: Record<FindingStatus, string> = {
  POTENTIAL_MANIPULATION: "bg-man",
  INCONSISTENCY: "bg-inc",
  OBSERVATION: "bg-obs",
};

export function StatusBadge({ status, className }: { status: FindingStatus; compact?: boolean; className?: string }) {
  const m = STATUS_META[status];
  return (
    <span title={m.meaning} className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12.5px] font-bold", m.text, m.bg, className)}>
      <Dot className={DOT[status]} />
      {m.label}
    </span>
  );
}

const RISK: Record<RiskLevel, { label: string; dot: string; text: string }> = {
  high: { label: "High risk", dot: "bg-man", text: "text-man bg-man-dim" },
  medium: { label: "Medium risk", dot: "bg-inc", text: "text-inc bg-inc-dim" },
  low: { label: "Low risk", dot: "bg-ok", text: "text-ok bg-ok-dim" },
  undetermined: { label: "Risk unclear", dot: "bg-ink-3", text: "text-ink-2 bg-raised" },
};

export function RiskPlate({ risk, assessed = true, large }: { risk: RiskLevel; assessed?: boolean; large?: boolean }) {
  const r = assessed ? RISK[risk] : { label: "Not checked yet", dot: "bg-ink-3", text: "text-ink-3 bg-raised" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full font-bold", large ? "px-3.5 py-1 text-[16px]" : "px-2.5 py-0.5 text-[13px]", r.text)}>
      <Dot className={r.dot} />
      {r.label}
    </span>
  );
}

export function HumanReviewPlate() {
  return <span className="text-[14px] font-medium text-ink-2">👀 Needs human review</span>;
}

const PROC: Record<ProcessingStatus, { label: string; cls: string }> = {
  pending: { label: "Waiting", cls: "text-ink-3" },
  processing: { label: "Working on it", cls: "text-ink-2" },
  ok: { label: "Read fine", cls: "text-ok" },
  degraded: { label: "Read with problems", cls: "text-inc" },
  unsupported: { label: "Not supported", cls: "text-ink-2" },
  failed: { label: "Couldn't be read", cls: "text-man" },
};

export function ProcBadge({ status }: { status: ProcessingStatus }) {
  const p = PROC[status] ?? PROC.pending;
  return <span className={cn("text-[14px]", p.cls)}>{p.label}</span>;
}

const REVIEW: Record<ReviewDecision, { label: string; cls: string }> = {
  pending: { label: "Not reviewed yet", cls: "text-ink-3" },
  confirmed: { label: "Confirmed", cls: "text-ink font-medium" },
  dismissed: { label: "Dismissed", cls: "text-ink-3 line-through" },
  escalated: { label: "Escalated", cls: "text-inc font-medium" },
};

export function ReviewBadge({ decision }: { decision: ReviewDecision }) {
  const r = REVIEW[decision];
  return <span className={cn("text-[13px]", r.cls)}>{r.label}</span>;
}

export function SeverityText({ severity }: { severity: Severity }) {
  return <span className="text-[13px] text-ink-3">Severity: {severity}</span>;
}

export function ConfidenceMeter({ value, label = "Confidence", low, words }: { value: number; label?: string; low?: boolean; words?: boolean }) {
  const v = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span title={`${label}: ${v}%`} className={cn("whitespace-nowrap text-[13px]", low ? "font-medium text-inc" : "text-ink-3")}>
      {v}%{words ? " confidence" : ""}
      {low ? " (low)" : ""}
      {!words && <span className="sr-only"> {label}</span>}
    </span>
  );
}
