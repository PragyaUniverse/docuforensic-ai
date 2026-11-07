/** Seen before, Verify this report, verification letters and the reviewers' track record. */
import type { BBox } from "./types";

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, { credentials: "include", ...init });
  } catch {
    throw new Error("The analysis service is not reachable. Check that it's running.");
  }
  if (!res.ok) {
    let detail = `The service returned HTTP ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface SeenPlace {
  doc_id: string;
  filename: string | null;
  doc_type: string | null;
  page: number;
  bbox: BBox;
  field_id?: string | null;
  case_id?: string;
}

export interface SeenElement {
  kind: "photo" | "signature" | "phone" | "email" | "bank_account_number" | "pan_number" | "id_number";
  label: string;
  strong: boolean;
  value: string | null;
  similarity: number;
  here: SeenPlace;
  there: SeenPlace;
}

export interface SeenGroup {
  case_id: string;
  case_name: string;
  created_at: string;
  applicant_here: string | null;
  applicant_there: string | null;
  same_applicant: boolean;
  elements: SeenElement[];
}

export interface SeenBefore {
  case_id: string;
  checked_cases: number;
  fingerprints: number;
  groups: SeenGroup[];
}

export interface ReportCheck {
  result: "original" | "modified" | "unknown" | "not_pdf";
  message: string;
  sha256: string;
  filename: string | null;
  size_bytes: number;
  case_id?: string | null;
  case_name?: string | null;
  issued_at?: string;
  entry_seq?: number;
  variant?: "full" | "redacted";
  chain?: { ok: boolean; entries_checked: number; first_bad_seq: number | null; reason: string | null };
}

export interface Letter {
  available: boolean;
  lang: "en" | "hi";
  to?: string;
  subject?: string;
  body?: string;
  about_document?: string;
  questions?: number;
  note?: string;
  message?: string;
}

export interface TrackRow {
  check: string;
  flagged: number;
  decided: number;
  confirmed: number;
  dismissed: number;
  escalated: number;
  dismissal_rate: number | null;
}

export const featuresApi = {
  seenBefore: (caseId: string) => send<SeenBefore>(`/cases/${encodeURIComponent(caseId)}/seen-before`),
  verifyReport: (file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return send<ReportCheck>("/verify-report", { method: "POST", body: form });
  },
  letter: (findingId: string, lang: "en" | "hi") =>
    send<Letter>(`/findings/${encodeURIComponent(findingId)}/verification-request?lang=${lang}`),
  trackRecord: () => send<{ min_decisions: number; checks: TrackRow[] }>("/analytics/track-record"),
  pageImageUrl: (caseId: string, docId: string, page: number) =>
    `${BASE}/api/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(docId)}/pages/${page}/image`,
};

/** Plain names for check ids, for tables that list checks. */
export const CHECK_NAMES: Record<string, string> = {
  "visual.ela": "Compression response (ELA)",
  "visual.noise": "Background noise",
  "visual.overwrite": "Overwritten value",
  "visual.font_consistency": "Typography",
  "visual.alignment": "Alignment",
  "visual.copy_move": "Copied regions",
  "visual.photo_insert": "Inserted photo",
  "visual.signature_reuse": "Reused signature",
  "pdf.text_vs_pixels": "PDF text vs pixels",
  "metadata.pdf_dates": "PDF dates",
  "context.amount_in_words": "Figures vs words",
  "context.arithmetic_salary": "Salary arithmetic",
  "context.arithmetic_balance": "Running balance",
  "crosscase.repeated_element": "Seen in another application",
};

export function checkName(id: string): string {
  if (CHECK_NAMES[id]) return CHECK_NAMES[id];
  const tail = id.split(".").pop() ?? id;
  return tail.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
