import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  return `${Math.round(v * 100)}%`;
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function shortHash(h: string | null | undefined, n = 12): string {
  if (!h) return "n/a";
  return h.length > n ? `${h.slice(0, n)}…` : h;
}

const ACRONYMS: Record<string, string> = {
  hra: "HRA",
  pan: "PAN",
  dob: "DOB",
  ifsc: "IFSC",
  id: "ID",
  ela: "ELA",
  pdf: "PDF",
  ocr: "OCR",
  llm: "LLM",
  exif: "EXIF",
};

export function humanize(s: string | null | undefined): string {
  if (!s) return "";
  const words = s
    .replace(/[_.]+/g, " ")
    .trim()
    .split(/\s+/)
    .map((w) => ACRONYMS[w.toLowerCase()] ?? w);
  const out = words.join(" ");
  return out.charAt(0).toUpperCase() + out.slice(1);
}

export function fmtBBox(b: { x0: number; y0: number; x1: number; y1: number } | null | undefined) {
  if (!b) return "no region";
  return `[${Math.round(b.x0)}, ${Math.round(b.y0)}, ${Math.round(b.x1)}, ${Math.round(b.y1)}]`;
}
