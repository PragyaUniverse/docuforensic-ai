import { Eye, Split, ShieldAlert, type LucideIcon } from "lucide-react";
import type {
  BBox,
  Document,
  EvidenceItem,
  Field,
  Finding,
  FindingCategory,
  FindingStatus,
  Severity,
} from "@/api/types";

export const STATUS_ORDER: FindingStatus[] = ["POTENTIAL_MANIPULATION", "INCONSISTENCY", "OBSERVATION"];

export const STATUS_META: Record<
  FindingStatus,
  { label: string; short: string; icon: LucideIcon; text: string; bg: string; border: string; stroke: string; meaning: string }
> = {
  OBSERVATION: {
    label: "Observation",
    short: "OBS",
    icon: Eye,
    text: "text-obs",
    bg: "bg-obs-dim",
    border: "border-obs",
    stroke: "#5aa9ff",
    meaning: "A measurable fact about the document. It makes no claim about intent.",
  },
  INCONSISTENCY: {
    label: "Inconsistency",
    short: "INC",
    icon: Split,
    text: "text-inc",
    bg: "bg-inc-dim",
    border: "border-inc",
    stroke: "#f6b12d",
    meaning: "Two values disagree, within a document or across documents.",
  },
  POTENTIAL_MANIPULATION: {
    label: "Potential manipulation",
    short: "MAN",
    icon: ShieldAlert,
    text: "text-man",
    bg: "bg-man-dim",
    border: "border-man",
    stroke: "#ff5a4f",
    meaning: "A hypothesis from forensic signals. It needs human review and is not confirmed.",
  },
};

export const CATEGORY_LABEL: Record<FindingCategory, string> = {
  visual: "Visual",
  structural: "Structural",
  contextual: "Contextual",
  cross_document: "Cross-document",
  metadata: "Metadata",
};

const SEV: Record<Severity, number> = { high: 3, medium: 2, low: 1, info: 0 };

export function sortFindings(list: Finding[]): Finding[] {
  return [...list].sort((a, b) => {
    const s = STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status);
    if (s) return s;
    const v = SEV[b.severity] - SEV[a.severity];
    if (v) return v;
    return (b.fused_score ?? b.confidence) - (a.fused_score ?? a.confidence);
  });
}

export function findingLabels(list: Finding[]): Map<string, string> {
  const m = new Map<string, string>();
  sortFindings(list).forEach((f, i) => m.set(f.id, `F-${String(i + 1).padStart(2, "0")}`));
  return m;
}

export interface Region {
  finding: Finding;
  bbox: BBox;
  primary: boolean;
}

/** Every region of a page that a finding points at, including evidence on other documents. */
export function regionsForPage(findings: Finding[], docId: string, page: number): Region[] {
  const out: Region[] = [];
  for (const f of findings) {
    if (f.doc_id === docId && f.page === page && f.bbox) out.push({ finding: f, bbox: f.bbox, primary: true });
    for (const ev of f.evidence) {
      if (ev.doc_id === docId && ev.page === page && ev.bbox) {
        const dup = out.some(
          (r) =>
            r.finding.id === f.id &&
            Math.abs(r.bbox.x0 - ev.bbox!.x0) < 2 &&
            Math.abs(r.bbox.y0 - ev.bbox!.y0) < 2 &&
            Math.abs(r.bbox.x1 - ev.bbox!.x1) < 2,
        );
        if (!dup) out.push({ finding: f, bbox: ev.bbox, primary: false });
      }
    }
  }
  return out;
}

export interface LocatedSource {
  key: string;
  docId: string;
  page: number;
  bbox: BBox;
  value: string | null;
  label: string;
  field: Field | null;
  evidence: EvidenceItem | null;
}

function dataValue(ev: EvidenceItem): string | null {
  const d = ev.data ?? {};
  for (const k of ["value", "value_raw", "raw", "text", "field_value"]) {
    const v = d[k];
    if (typeof v === "string" || typeof v === "number") return String(v);
  }
  return null;
}

/** Resolves the located sources of a finding, for side-by-side comparison. */
export function comparisonSources(f: Finding, fieldsById: Map<string, Field>): LocatedSource[] {
  const out: LocatedSource[] = [];
  const seen = new Set<string>();
  const push = (s: LocatedSource) => {
    const k = s.field ? `f:${s.field.id}` : `b:${s.docId}:${s.page}:${Math.round(s.bbox.x0)}:${Math.round(s.bbox.y0)}`;
    if (seen.has(k)) return;
    seen.add(k);
    out.push({ ...s, key: k });
  };
  for (const ev of f.evidence) {
    const field = ev.field_id ? (fieldsById.get(ev.field_id) ?? null) : null;
    const docId = ev.doc_id ?? field?.doc_id;
    const page = ev.page ?? field?.page;
    const bbox = ev.bbox ?? field?.bbox;
    if (!docId || page === null || page === undefined || !bbox) continue;
    push({
      key: "",
      docId,
      page,
      bbox,
      value: dataValue(ev) ?? field?.value_raw ?? null,
      label: field?.label_raw ?? ev.label,
      field,
      evidence: ev,
    });
  }
  for (const id of f.related_field_ids) {
    const field = fieldsById.get(id);
    if (!field) continue;
    push({
      key: "",
      docId: field.doc_id,
      page: field.page,
      bbox: field.bbox,
      value: field.value_raw,
      label: field.label_raw ?? field.name,
      field,
      evidence: null,
    });
  }
  return out;
}

export function docName(d: Document | undefined, fallback = "Unknown document"): string {
  return d?.filename ?? fallback;
}

export interface DiffPart {
  text: string;
  changed: boolean;
}

/** Character LCS diff, used to expose subtle variants such as a one-word address change. */
export function charDiff(a: string, b: string): [DiffPart[], DiffPart[]] {
  if (a.length > 240 || b.length > 240) {
    return [[{ text: a, changed: a !== b }], [{ text: b, changed: a !== b }]];
  }
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const pa: DiffPart[] = [];
  const pb: DiffPart[] = [];
  const add = (arr: DiffPart[], ch: string, changed: boolean) => {
    const last = arr[arr.length - 1];
    if (last && last.changed === changed) last.text += ch;
    else arr.push({ text: ch, changed });
  };
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) {
      add(pa, a[i], false);
      add(pb, b[j], false);
      i++;
      j++;
    } else if (j >= m || (i < n && dp[i + 1][j] >= dp[i][j + 1])) {
      add(pa, a[i], true);
      i++;
    } else {
      add(pb, b[j], true);
      j++;
    }
  }
  return [pa, pb];
}
