import type { Case } from "@/api/types";

/** A short, stable reference for a case, derived from its id. */
export function caseCode(id: string): string {
  return `DF-${id.replace(/^case_/, "").slice(0, 6).toUpperCase()}`;
}

export function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function caseState(c: Pick<Case, "status">, toReview?: number): { label: string; tone: "cyan" | "green" | "amber" | "muted" | "red" } {
  if (c.status === "running") return { label: "Analyzing", tone: "cyan" };
  if (c.status === "failed") return { label: "Analysis stopped", tone: "red" };
  if (c.status !== "complete") return { label: "Awaiting evidence", tone: "muted" };
  if (toReview === 0) return { label: "Review complete", tone: "green" };
  return { label: "Investigation active", tone: "cyan" };
}
