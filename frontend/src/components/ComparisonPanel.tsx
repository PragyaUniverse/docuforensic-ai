import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { Document, Field, Finding } from "@/api/types";
import { STATUS_META, charDiff, comparisonSources, type DiffPart, type LocatedSource } from "@/lib/findings";
import { cn, fmtBBox, humanize, pct } from "@/lib/utils";
import { PageCrop } from "./PageCrop";
import { ConfidenceMeter, StatusBadge } from "./StatusBadge";
import { DataList } from "./DataList";
import { Explanation } from "./FindingCard";

function num(s: string | null): number | null {
  if (!s) return null;
  const cleaned = s.replace(/[^0-9.-]/g, "");
  if (!cleaned || !/\d/.test(cleaned)) return null;
  // Only treat the values as amounts when digits dominate, so dates and IDs aren't subtracted.
  if (/[a-zA-Z/]/.test(s.replace(/\b(rs|inr)\b\.?/gi, ""))) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function Parts({ parts, tone }: { parts: DiffPart[]; tone: string }) {
  return (
    <>
      {parts.map((p, i) =>
        p.changed ? (
          <mark key={i} className={cn("bg-transparent underline decoration-2 underline-offset-[5px]", tone)}>
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}

function SourceCard({
  caseId,
  source,
  doc,
  parts,
  stroke,
  tone,
}: {
  caseId: string;
  source: LocatedSource;
  doc: Document | undefined;
  parts: DiffPart[] | null;
  stroke: string;
  tone: string;
}) {
  const conf = source.field?.confidence;
  const q = new URLSearchParams({ doc: source.docId, page: String(source.page) });
  if (source.field) q.set("field", source.field.id);
  return (
    <div className="flex min-w-0 flex-1 flex-col border border-line bg-raised">
      <div className="flex items-start justify-between gap-2 border-b border-line px-3 py-2">
        <div className="min-w-0">
          <div className="eyebrow">{humanize(doc?.doc_type ?? "document")}</div>
          <div className="truncate font-mono text-xs text-ink-2">{doc?.filename ?? source.docId}</div>
        </div>
        <Link
          to={{ pathname: `/cases/${caseId}/viewer`, search: q.toString() }}
          className="flex shrink-0 items-center gap-0.5 text-xs text-ink-2 underline-offset-2 hover:text-ink hover:underline"
        >
          Open source <ArrowUpRight className="size-3" aria-hidden />
        </Link>
      </div>
      <div className="px-3 pb-2 pt-3">
        <div className="text-xs text-ink-3">{source.label}</div>
        {(parts || source.value) && (
          <div className="mt-0.5 break-words font-mono text-[19px] font-medium leading-snug text-ink">
            {parts ? <Parts parts={parts} tone={tone} /> : source.value}
          </div>
        )}
      </div>
      <div className="mt-auto border-t border-line">
        <PageCrop caseId={caseId} doc={doc} page={source.page} bbox={source.bbox} stroke={stroke} className="max-h-44" />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-3 py-1.5 font-mono text-[11px] text-ink-3">
        <span>page {source.page + 1}</span>
        <span>{fmtBBox(source.bbox)}</span>
        {conf !== undefined && <span>OCR conf {pct(conf)}</span>}
      </div>
    </div>
  );
}

export function ComparisonPanel({
  caseId,
  finding,
  docs,
  fieldsById,
  label,
  compact,
}: {
  caseId: string;
  finding: Finding;
  docs: Map<string, Document>;
  fieldsById: Map<string, Field>;
  label?: string;
  compact?: boolean;
}) {
  const sources = useMemo(() => comparisonSources(finding, fieldsById), [finding, fieldsById]);
  const m = STATUS_META[finding.status];
  // Reuse findings flag two regions for being identical, not for differing.
  const sameExpected = /signature_reuse|copy_move/.test(finding.detector);

  const diff = useMemo(() => {
    if (sources.length !== 2 || !sources[0].value || !sources[1].value) return null;
    return charDiff(sources[0].value, sources[1].value);
  }, [sources]);

  const delta = useMemo(() => {
    if (sources.length !== 2) return null;
    const a = num(sources[0].value);
    const b = num(sources[1].value);
    if (a === null || b === null) return null;
    return Math.abs(a - b);
  }, [sources]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {label && <span className="font-mono text-xs text-ink-3">{label}</span>}
        <StatusBadge status={finding.status} />
        {finding.discrepancy_type && <span className="font-mono text-[11px] text-ink-2">{finding.discrepancy_type}</span>}
        <span className="ml-auto">
          <ConfidenceMeter value={finding.confidence} />
        </span>
      </div>
      <h3 className={cn("display", compact ? "text-[15px]" : "text-lg")}>{finding.title}</h3>

      {sources.length === 0 ? (
        <p className="border border-line bg-raised p-3 text-ink-2">
          This finding records no located source fields, so no side-by-side view is available.
        </p>
      ) : sources.length === 2 ? (
        <div className={cn("flex items-stretch gap-2", compact ? "flex-col" : "flex-col md:flex-row")}>
          <SourceCard caseId={caseId} source={sources[0]} doc={docs.get(sources[0].docId)} parts={diff?.[0] ?? null} stroke={m.stroke} tone={m.text} />
          <div className="flex shrink-0 flex-col items-center justify-center gap-1 px-1 py-1">
            <span
              role="img"
              aria-label={sameExpected ? "matches" : "does not match"}
              className={cn("font-mono text-[26px] font-medium leading-none", m.text)}
            >
              {sameExpected ? "=" : "≠"}
            </span>
            {delta !== null && delta > 0 && (
              <span className={cn("font-mono text-[11px]", m.text)}>
                {delta.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            )}
          </div>
          <SourceCard caseId={caseId} source={sources[1]} doc={docs.get(sources[1].docId)} parts={diff?.[1] ?? null} stroke={m.stroke} tone={m.text} />
        </div>
      ) : (
        <div className={cn("grid gap-2", compact ? "grid-cols-1" : "md:grid-cols-2 xl:grid-cols-3")}>
          {sources.map((s) => (
            <SourceCard key={s.key} caseId={caseId} source={s} doc={docs.get(s.docId)} parts={null} stroke={m.stroke} tone={m.text} />
          ))}
        </div>
      )}

      <div className="max-w-[80ch]">
        <Explanation text={finding.explanation} />
      </div>
      {finding.evidence.some((e) => Object.keys(e.data ?? {}).length > 0 && e.kind === "raw_value") && (
        <div className="flex flex-col gap-2 border-t border-line pt-2">
          {finding.evidence
            .filter((e) => Object.keys(e.data ?? {}).length > 0 && e.kind === "raw_value")
            .map((e, i) => (
              <div key={i}>
                <div className="mb-1 text-xs text-ink-3">{e.label}</div>
                <DataList data={e.data} />
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
