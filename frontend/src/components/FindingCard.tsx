import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import type { Document, EvidenceItem, Finding, ReasoningProvenance, ReviewDecision } from "@/api/types";
import { CATEGORY_LABEL, STATUS_META, splitExplanation } from "@/lib/findings";
import { docSays } from "@/lib/assistant";
import { getReviewer, setReviewer } from "@/lib/reviewer";
import { cn, fmtBBox, fmtTime } from "@/lib/utils";
import { Button } from "./ui/button";
import { ConfidenceMeter, ReviewBadge, StatusBadge } from "./StatusBadge";
import { DataList } from "./DataList";
import { PageCrop } from "./PageCrop";

export function Provenance({ r }: { r: ReasoningProvenance }) {
  const who = [r.provider, r.model].filter(Boolean).join(" / ");
  const text =
    r.mode === "live_llm"
      ? `Explanation includes notes from an AI model${who ? ` (${who})` : ""}.`
      : r.mode === "demo_cache"
        ? `Explanation includes AI notes recorded in an earlier run${who ? ` (${who})` : ""}, not a live answer.`
        : "Explanation written from fixed rules. No AI was used.";
  return <span className="text-[13px] text-ink-3">{text}</span>;
}

/** Leads with what happened. The longer reasoning stays one click away. */
export function Explanation({ text }: { text: string }) {
  const parts = splitExplanation(text);
  const raw = parts.find((p) => !p.heading)?.text ?? "";
  const [lead, otherSignals] = raw.split(/\s*Other signals on this region\.?:?\s*/);
  const whyRaw = parts.find((p) => p.heading === "Why it matters")?.text ?? "";
  const [why, corroboration] = whyRaw.split(/\s*Corroboration:\s*/);
  const ai = parts.find((p) => p.heading?.startsWith("AI reasoning"));
  const hasMore = otherSignals || corroboration || ai;
  return (
    <div className="flex flex-col gap-2 text-ink-2">
      <p className="text-ink">{lead}</p>
      {why && <p>{why}</p>}
      {hasMore && (
        <details className="text-[14px]">
          <summary>Read more</summary>
          <div className="mt-1.5 flex flex-col gap-2">
            {otherSignals && (
              <div>
                <div className="font-medium text-ink">Other checks on this spot</div>
                <p>{otherSignals}</p>
              </div>
            )}
            {corroboration && <p>{corroboration}</p>}
            {ai && (
              <div>
                <div className="font-medium text-ink">AI notes</div>
                <p>{ai.text}</p>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

function EvidenceBlock({
  ev,
  caseId,
  docs,
  stroke,
}: {
  ev: EvidenceItem;
  caseId: string;
  docs: Map<string, Document>;
  stroke: string;
}) {
  const [failed, setFailed] = useState(false);
  const hasImage = ev.uri && !failed;
  const doc = ev.doc_id ? docs.get(ev.doc_id) : undefined;
  const measurement = ev.kind === "raw_value" || ev.kind === "metadata" || ev.kind === "field_ref";
  const location = ev.doc_id && (
    <span className="text-[13px] text-ink-3">
      {doc?.filename ?? ev.doc_id}
      {ev.page !== null && `, page ${ev.page + 1}`}
    </span>
  );

  // Measurements lead with the numbers; their source crop is a small reference.
  if (measurement) {
    return (
      <figure className="flex gap-2 rounded-md border border-line bg-ground p-2">
        <figcaption className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-[13px] text-ink-2">{ev.label}</span>
          <DataList data={ev.data} />
          {location}
        </figcaption>
        {hasImage && (
          <img
            src={api.fileUrl(ev.uri!)}
            alt=""
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-auto max-h-16 w-20 shrink-0 self-start bg-white object-contain"
          />
        )}
      </figure>
    );
  }

  return (
    <figure className="overflow-hidden rounded-md border border-line bg-ground">
      {hasImage ? (
        <img
          src={api.fileUrl(ev.uri!)}
          alt={ev.label}
          loading="lazy"
          onError={() => setFailed(true)}
          className={cn("max-h-56 w-full object-contain", ev.kind === "heatmap" ? "bg-[#ffffff]" : "bg-white")}
        />
      ) : ev.doc_id && ev.page !== null && ev.bbox ? (
        <PageCrop caseId={caseId} doc={doc} page={ev.page} bbox={ev.bbox} stroke={stroke} className="max-h-48" />
      ) : ev.uri ? (
        <div className="p-2 text-[13px] text-ink-3">Evidence image could not be loaded: {ev.uri}</div>
      ) : null}
      <figcaption className="flex flex-col gap-1 px-2 py-1.5">
        <span className="text-[13px] text-ink-2">{ev.label}</span>
        {location}
        <DataList data={ev.data} />
      </figcaption>
    </figure>
  );
}

const ACTIONS: { d: ReviewDecision; label: string }[] = [
  { d: "confirmed", label: "Confirm" },
  { d: "dismissed", label: "Dismiss" },
  { d: "escalated", label: "Escalate" },
];

export function FindingCard({
  finding,
  label,
  caseId,
  docs,
  selected,
  labelsById,
  onSelect,
  onSelectRelated,
  onCompare,
}: {
  finding: Finding;
  label: string;
  caseId: string;
  docs: Map<string, Document>;
  selected: boolean;
  labelsById: Map<string, string>;
  onSelect: () => void;
  onSelectRelated: (id: string) => void;
  onCompare?: () => void;
}) {
  const m = STATUS_META[finding.status];
  const ref = useRef<HTMLElement>(null);
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [reviewer, setName] = useState(getReviewer);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 2200);
    return () => window.clearTimeout(timer);
  }, [saved]);

  useEffect(() => {
    if (!selected) return;
    // Wait for the previously open card to collapse, or this position would be out of date and the
    // list could end up scrolled past its content.
    const timer = window.setTimeout(() => ref.current?.scrollIntoView({ block: "start", behavior: "smooth" }), 240);
    return () => window.clearTimeout(timer);
  }, [selected]);

  const review = useMutation({
    mutationFn: (d: ReviewDecision) => api.reviewFinding(finding.id, d, reviewer.trim() || "examiner", note.trim()),
    onSuccess: (updated) => {
      docSays(`Noted: ${updated.review.decision}. That's in the history now.`);
      setReviewer(reviewer.trim() || "examiner");
      setNote("");
      setSaved(true);
      qc.invalidateQueries({ queryKey: ["findings", caseId] });
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
      qc.invalidateQueries({ queryKey: ["dossier", caseId] });
    },
  });

  const doc = finding.doc_id ? docs.get(finding.doc_id) : undefined;
  const dismissed = finding.review.decision === "dismissed";

  const dismissedCls = dismissed && "opacity-60";
  return (
    <article ref={ref} className={cn("border-b border-line transition-colors duration-150", selected ? "bg-raised" : "bg-panel")}>
      <button
        type="button"
        aria-expanded={selected}
        onClick={onSelect}
        className={cn("flex w-full cursor-pointer flex-col gap-0.5 px-4 py-3 text-left transition-colors duration-150 hover:bg-hover", dismissedCls)}
      >
        <span className="flex flex-wrap items-center gap-x-2">
          <StatusBadge status={finding.status} />
          <span className="ml-auto text-[13px] text-ink-3">{label}</span>
        </span>
        <span className="font-medium leading-snug text-ink">{finding.title}</span>
        <span className="flex flex-wrap items-center gap-x-2 text-[13px] text-ink-3">
          {doc && (
            <span>
              {doc.filename}
              {finding.page !== null && `, page ${finding.page + 1}`}
            </span>
          )}
          {finding.review.decision !== "pending" && <ReviewBadge decision={finding.review.decision} />}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {selected && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-3.5 px-4 pb-4">
              <Explanation text={finding.explanation} />
              <ConfidenceMeter words value={finding.fused_score ?? finding.confidence} />

              {onCompare && (
                <Button size="sm" onClick={onCompare} className="self-start">
                  Compare side by side
                </Button>
              )}

              <section className="rounded-lg border border-line bg-panel shadow-sm p-3" aria-label="Your decision">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h4 className="eyebrow">Your decision</h4>
                  {saved && (
                    <span role="status" className="fade-in flex items-center gap-1 text-[13px] font-medium text-ok">
                      <Check className="pop size-3.5" aria-hidden /> Saved
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {ACTIONS.map(({ d, label: l }) => (
                    <Button
                      key={d}
                      size="sm"
                      disabled={review.isPending}
                      aria-pressed={finding.review.decision === d}
                      className={cn(finding.review.decision === d && "border-accent bg-obs-dim text-accent")}
                      onClick={() => review.mutate(d)}
                    >
                      {l}
                    </Button>
                  ))}
                </div>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  aria-label="Optional note"
                  placeholder="Add a note (optional)"
                  className="mt-2 h-8 w-full rounded-md border border-line-strong bg-panel px-2 text-[14px] text-ink placeholder:text-ink-3"
                />
                <label className="mt-1.5 flex items-center gap-1.5 text-[13px] text-ink-3">
                  Reviewing as
                  <input
                    value={reviewer}
                    onChange={(e) => setName(e.target.value)}
                    aria-label="Reviewer name"
                    placeholder="Your name"
                    className="h-7 min-w-0 flex-1 rounded-lg border border-line bg-panel shadow-sm px-1.5 text-[13px] text-ink placeholder:text-ink-3"
                  />
                </label>
                {finding.review.at && (
                  <p className="mt-2 text-[13px] text-ink-3">
                    <ReviewBadge decision={finding.review.decision} /> by {finding.review.reviewer}, {fmtTime(finding.review.at)}
                    {finding.review.note && <span className="block text-ink-2">"{finding.review.note}"</span>}
                  </p>
                )}
                {review.isError && (
                  <p role="alert" className="mt-1.5 text-[13px] text-man">
                    That didn't save: {(review.error as Error).message}
                  </p>
                )}
              </section>

              {finding.benign_alternatives.length > 0 && (
                <section>
                  <h4 className="eyebrow mb-1">Could be innocent if</h4>
                  <ul className="list-disc space-y-0.5 pl-4 text-[14px] text-ink-2 marker:text-ink-3">
                    {finding.benign_alternatives.slice(0, 3).map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                </section>
              )}

              {finding.recommended_verification.length > 0 && (
                <section>
                  <h4 className="eyebrow mb-1">How to check</h4>
                  <ul className="list-disc space-y-0.5 pl-4 text-[14px] text-ink-2 marker:text-ink-3">
                    {finding.recommended_verification.slice(0, 3).map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                </section>
              )}

              {finding.evidence.length > 0 && (
                <details className="text-[14px]">
                  <summary>Show the evidence ({finding.evidence.length})</summary>
                  <div className="mt-2 flex flex-col gap-2">
                    {finding.evidence.map((ev, i) => (
                      <EvidenceBlock key={i} ev={ev} caseId={caseId} docs={docs} stroke={m.stroke} />
                    ))}
                  </div>
                </details>
              )}

              {finding.related_finding_ids.length > 0 && (
                <div className="text-[14px] text-ink-2">
                  Related:{" "}
                  {finding.related_finding_ids.map((id, i) => (
                    <span key={id}>
                      {i > 0 && ", "}
                      <button type="button" className="link cursor-pointer" onClick={() => onSelectRelated(id)}>
                        {labelsById.get(id) ?? id}
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <details className="text-[14px]">
                <summary>Technical details</summary>
                <dl className="mt-1.5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[13px] text-ink-2">
                  <dt className="text-ink-3">Check</dt>
                  <dd className="code break-all">{finding.detector}</dd>
                  <dt className="text-ink-3">Where it looked</dt>
                  <dd>{CATEGORY_LABEL[finding.category]}</dd>
                  <dt className="text-ink-3">Severity</dt>
                  <dd>{finding.severity}</dd>
                  {finding.fused_score !== null && (
                    <>
                      <dt className="text-ink-3">Combined score</dt>
                      <dd>{Math.round(finding.fused_score * 100)}%</dd>
                    </>
                  )}
                  <dt className="text-ink-3">Check's own confidence</dt>
                  <dd>{Math.round(finding.confidence * 100)}%</dd>
                  {finding.bbox && (
                    <>
                      <dt className="text-ink-3">Region (pixels)</dt>
                      <dd className="code">{fmtBBox(finding.bbox)}</dd>
                    </>
                  )}
                </dl>
                <div className="mt-1.5">
                  <Provenance r={finding.reasoning} />
                </div>
              </details>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
}
